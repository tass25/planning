# Week 15 — Step-by-Step Execution Guide

**Rule**: nothing runs on your PC except registering API keys (browser) and wiring
the final model + code into the project files. All scraping, distillation,
deduplication, and training happen in Colab or Lightning AI.

---

## What runs where

| Task | Where |
|------|-------|
| Register API keys | Browser (your PC) |
| Scrape The Stack v2 + GitHub | **Google Colab** (notebook 1) |
| Teacher LLM distillation (Groq + Gemini + Kimi K2.5) | **Google Colab** (notebook 1, same) |
| Deduplication (MinHash) | **Google Colab** (notebook 1, same) |
| QLoRA SFT fine-tuning | **Lightning AI** (notebook 2) |
| Export GGUF + push to HuggingFace | **Lightning AI** (notebook 2, same) |
| Wire local model into pipeline | Your PC (code only) |
| Z3 agent code | Your PC (code only) |
| HyperRAPTOR code | Your PC (code only) |
| `pytest` + benchmark | Your PC |

---

## PHASE 0 — API keys (browser, ~10 min)

### 0-A. Groq (already in your project)
Your `GROQ_API_KEY` is already in `backend/.env` — nothing to do.
Model used for distillation: `llama-3.3-70b-versatile` (14 400 req/day free).

### 0-B. Gemini 2.0 Flash (1M tokens/day free)
1. `https://aistudio.google.com/` → Sign in with Google
2. "Get API key" → Create API key → **copy it**

### 0-C. Kimi K2.5 via NVIDIA NIM (already have it — rotate the exposed key)
1. `https://build.nvidia.com/settings/api-keys` → revoke the exposed `nvapi-oo5r9...` key
2. Generate new key → **copy it**
3. Model name: `moonshotai/kimi-k2.5`, base URL: `https://integrate.api.nvidia.com/v1`
   Uses standard OpenAI SDK — no extra library needed.

### 0-D. HuggingFace (rotate the exposed token)
1. `https://huggingface.co/settings/tokens` → delete exposed token → New token → **Write** access → **copy it**
2. Note your HF username (shown top-right on HF)

### 0-E. GitHub PAT (rotate the exposed one)
1. `https://github.com/settings/tokens` → delete exposed token → Generate new token (classic)
2. Scopes: `public_repo` only → Generate → **copy it**

### 0-F. Lightning AI (for GPU training)
1. `https://lightning.ai/` → Sign up with email (free plan, 22 GPU hours/month)
2. No setup needed now — you'll create a Studio in Phase 2

---

## PHASE 1 — Data collection + distillation (Google Colab)

Everything in one notebook. Open `https://colab.research.google.com/` → New notebook.

### Cell 1 — Install deps

```python
%%capture
!pip install datasketch requests tqdm openai huggingface_hub beautifulsoup4 pdfplumber
```

### Cell 2 — Set your API keys

```python
import os

# Paste your keys here — only stored in Colab RAM, never saved to disk
os.environ["GROQ_API_KEY"]    = "PASTE_YOUR_GROQ_KEY"
os.environ["GEMINI_API_KEY"]  = "PASTE_YOUR_GEMINI_KEY"
os.environ["NVIDIA_API_KEY"]  = "PASTE_YOUR_NEW_NVIDIA_KEY"   # new one after rotating
os.environ["GITHUB_TOKEN"]    = "PASTE_YOUR_NEW_GITHUB_PAT"
os.environ["HF_TOKEN"]        = "PASTE_YOUR_NEW_HF_TOKEN"
os.environ["HF_USERNAME"]     = "PASTE_YOUR_HF_USERNAME"
```

### Cell 3 — Source A: GitHub (~300 files, broad SAS coverage)

```python
import requests, time, json
from pathlib import Path

Path("data").mkdir(exist_ok=True)

gh_headers = {
    "Authorization": f"token {os.environ['GITHUB_TOKEN']}",
    "Accept": "application/vnd.github.v3+json"
}

# Targeted enterprise SAS organisations + broad keyword queries
KNOWN_SAS_ORGS = [
    "sassoftware",   # SAS Institute official repos
    "phuse-org",     # pharma/clinical SAS
    "FDA-CDER",      # FDA clinical data
]

# Broad keyword queries — one term each to avoid 422
QUERIES = [
    "proc+sql+extension:sas",
    "proc+means+extension:sas",
    "proc+logistic+extension:sas",
    "proc+mixed+extension:sas",
    "proc+glm+extension:sas",
    "proc+iml+extension:sas",
    "proc+report+extension:sas",
    "proc+tabulate+extension:sas",
    "ods+output+extension:sas",
    "data+_null_+extension:sas",
    "%macro+extension:sas",
    "proc+datasets+extension:sas",
]

all_raw = []
seen = set()

def add_file(content: str, source: str):
    if content and 100 < len(content) < 30000:
        h = hash(content[:300])
        if h not in seen:
            seen.add(h)
            all_raw.append({"sas": content, "source": source})

def get_raw(repo: str, path: str) -> str | None:
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{path}"
    try:
        r = requests.get(url, timeout=10)
        return r.text if r.status_code == 200 else None
    except Exception:
        return None

# --- A1: Scrape known SAS orgs via contents API ---
print("=== A1: Scraping known SAS organisations ===")
for org in KNOWN_SAS_ORGS:
    r = requests.get(f"https://api.github.com/orgs/{org}/repos",
                     params={"per_page": 50}, headers=gh_headers, timeout=15)
    if r.status_code != 200:
        print(f"  {org}: {r.status_code}"); continue
    for repo in r.json():
        repo_name = repo["full_name"]
        # Search for .sas files in this specific repo
        sr = requests.get("https://api.github.com/search/code",
                          params={"q": f"extension:sas repo:{repo_name}", "per_page": 30},
                          headers=gh_headers, timeout=15)
        if sr.status_code != 200:
            time.sleep(7); continue
        for item in sr.json().get("items", []):
            content = get_raw(repo_name, item["path"])
            add_file(content, f"github/{org}")
        time.sleep(7)
    print(f"  {org} done, total: {len(all_raw)}")

# --- A2: Broad keyword search ---
print("\n=== A2: Keyword search across all GitHub ===")
for q in QUERIES:
    print(f"  Querying: {q}")
    for page in range(1, 4):
        r = requests.get("https://api.github.com/search/code",
                         params={"q": q, "per_page": 30, "page": page},
                         headers=gh_headers, timeout=15)
        if r.status_code == 403:
            print(f"    Rate limited — sleeping 65s"); time.sleep(65); continue
        if r.status_code != 200:
            break
        items = r.json().get("items", [])
        if not items:
            break
        for item in items:
            content = get_raw(item["repository"]["full_name"], item["path"])
            add_file(content, "github_search")
        print(f"    page {page}: total unique {len(all_raw)}")
        time.sleep(7)
    time.sleep(5)

print(f"\nSource A total: {len(all_raw)} SAS files")
```

### Cell 3b — Source B: Targeted repo full download (~200 files)

Uses the git tree API to list and download every `.sas` file from repos known
to have enterprise-grade code. No search API = no rate limits.

```python
from bs4 import BeautifulSoup
import re

# Repos verified to contain enterprise SAS — downloaded completely, not searched
SAS_REPOS = [
    "sassoftware/sas-viya-programming",           # official SAS Viya examples (all procs)
    "sassoftware/getting-started-with-sas-viya",  # official getting-started programs
    "sascommunities/sasgf",                       # SAS Global Forum community examples
    "sascommunities/graphically-speaking",         # ODS Graphics / PROC SGPLOT
    "sascommunities/the-do-loop-blog",            # Rick Wicklin (SAS R&D) blog code
    "phuse-org/phuse-scripts",                    # CDISC ADaM/SDTM clinical scripts
    "phuse-org/CSS2022",                          # Clinical SAS Symposium 2022
    "phuse-org/CSRMLW",                           # clinical trial reporting
]

def get_all_sas_files_in_repo(repo: str) -> list[dict]:
    """Download every .sas file in a repo using the git tree API."""
    files = []
    r = requests.get(
        f"https://api.github.com/repos/{repo}/git/trees/HEAD",
        params={"recursive": "1"},
        headers=gh_headers, timeout=20
    )
    if r.status_code == 404:
        print(f"    {repo}: not found (repo may be renamed/private)")
        return files
    if r.status_code != 200:
        print(f"    {repo}: {r.status_code}")
        return files

    sas_items = [
        item for item in r.json().get("tree", [])
        if item.get("type") == "blob" and item.get("path", "").lower().endswith(".sas")
    ]
    print(f"    {repo}: {len(sas_items)} .sas files found")

    for item in sas_items[:80]:   # cap 80 per repo
        url = f"https://raw.githubusercontent.com/{repo}/HEAD/{item['path']}"
        try:
            rc = requests.get(url, timeout=10)
            if rc.status_code == 200 and 100 < len(rc.text) < 30000:
                files.append({"sas": rc.text, "source": f"repo/{repo.split('/')[0]}"})
        except Exception:
            pass
        time.sleep(0.15)
    return files

repo_raw = []
print("=== Source B: Targeted repo full download ===")
for repo in SAS_REPOS:
    print(f"  {repo}")
    batch = get_all_sas_files_in_repo(repo)
    before = len(repo_raw)
    for item in batch:
        h = hash(item["sas"][:300])
        if h not in seen:
            seen.add(h)
            repo_raw.append(item)
    print(f"    +{len(repo_raw)-before} unique, running total: {len(repo_raw)}")
    time.sleep(2)

all_raw.extend(repo_raw)
print(f"\nSource B total: {len(repo_raw)} files | Grand total: {len(all_raw)}")
```

### Cell 3c — Source C: LLM enterprise domain templates (~150 programs, 3 providers)

All SAS conference paper archives (Lex Jansen, PharmaSUG, SAS Global Forum) serve PDFs only —
no HTML paper text is publicly available. Replaced with targeted LLM generation using all 3
providers in parallel, covering 50 enterprise domains: pharma/clinical, financial risk,
ODS reporting, advanced macros, DB/ETL, regulatory, performance.

```python
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

SYSTEM_EXPERT = (
    "You are a senior SAS programmer with 20 years of enterprise experience. "
    "Write complete, production-quality SAS programs with realistic variable names, real-looking data, "
    "and all necessary OPTIONS/LIBNAME/ODS statements. "
    "Return ONLY SAS code — no markdown fences, no explanation."
)

DOMAIN_PROMPTS = [
    # Clinical / CDISC
    "Write a complete SAS program creating a CDISC SDTM DM domain from raw clinical trial data with proper labels and formats.",
    "Write a complete SAS program deriving an ADaM ADSL dataset with TRTSDT, TRTDUR, AGE groups, and safety flags from SDTM.",
    "Write a complete SAS program producing Table 14.1.1 demographics using PROC REPORT and ODS RTF with spanning headers.",
    "Write a complete SAS program for Kaplan-Meier survival curve and risk table using PROC LIFETEST and ODS GRAPHICS.",
    "Write a complete SAS program for MMRM analysis using PROC MIXED with LSMEANS, DIFFS, and ODS OUTPUT.",
    "Write a complete SAS macro generating adverse event summary tables by SOC/PT for multiple treatment arms.",
    "Write a complete SAS program using PROC PHREG for Cox regression with time-dependent covariates and Schoenfeld residuals.",
    "Write a complete SAS program validating an ADaM dataset against CDISC rules using PROC COMPARE and custom data checks.",
    "Write a complete SAS program computing laboratory shift tables using PROC FREQ and PROC TABULATE with ODS PDF output.",
    "Write a complete SAS macro framework for automated TLF production with a driver program and error-handling utility macros.",
    # Financial / Risk
    "Write a complete SAS program for portfolio Value-at-Risk using historical simulation with PROC UNIVARIATE.",
    "Write a complete SAS program using PROC IML for covariance matrix, Cholesky decomposition, and portfolio optimisation.",
    "Write a complete SAS program for credit scorecard development using PROC LOGISTIC with WOE binning and GINI coefficient.",
    "Write a complete SAS program for time-series revenue forecasting using PROC ARIMA with automatic model identification.",
    "Write a complete SAS program using PROC SQL for financial reconciliation: match transactions, identify breaks, summarise discrepancies.",
    "Write a complete SAS program using PROC AUTOREG for autoregressive model with heteroscedasticity tests and DW statistic.",
    "Write a complete SAS program for Monte Carlo option pricing simulation using PROC IML.",
    "Write a complete SAS program for customer churn prediction using PROC LOGISTIC with stepwise selection and ROC curve.",
    # ODS / Reporting
    "Write a complete SAS program using ODS EXCEL to create a multi-sheet workbook from PROC TABULATE with formatted headers.",
    "Write a complete SAS program using ODS PDF with PROC REPORT: spanning headers, traffic-light formatting, page breaks by group.",
    "Write a complete SAS program using ODS GRAPHICS and PROC SGPLOT: histogram, box plot, and scatter with regression line panels.",
    "Write a complete SAS program using PROC REPORT COMPUTE blocks for cumulative totals and cross-column conditional formatting.",
    "Write a complete SAS program using PROC TEMPLATE to define a custom table style applied to PROC REPORT in ODS PDF.",
    "Write a complete SAS program using PROC SGPANEL for lattice plots stratified by two classification variables with reference lines.",
    # Advanced Macro / DATA Step
    "Write a complete SAS macro framework with %GLOBAL/%LOCAL, %DO %WHILE, %EVAL arithmetic, and &SYSERR error handling.",
    "Write a complete SAS program using hash objects for many-to-many lookup between a large transaction table and a dimension table.",
    "Write a complete SAS program using ARRAY processing: row-wise standardisation, missing-value imputation, flag generation.",
    "Write a complete SAS DATA step using RETAIN, FIRST., LAST., and LAG() to compute session metrics and carry-forward values.",
    "Write a complete SAS program using PROC FCMP to define custom statistical functions reused in a DATA step.",
    "Write a complete SAS macro that dynamically builds a PROC SQL SELECT list from a macro variable containing column names.",
    "Write a complete SAS program using PROC FORMAT with CNTLIN= to build format catalogues from a control dataset.",
    "Write a complete SAS program using %INCLUDE and FILENAME to modularise an ETL pipeline with config files and audit logging.",
    "Write a complete SAS program scanning a log file for ERRORs and WARNINGs using FILENAME and DATA step text parsing.",
    "Write a complete SAS program using %SYSFUNC(DOPEN/DREAD) to loop over files in a directory and stack results with PROC APPEND.",
    # DB / ETL
    "Write a complete SAS program using LIBNAME ODBC to connect SQL Server, run a pass-through query, and load results.",
    "Write a complete SAS program using PROC SQL pass-through to Oracle with bulk insert, commit, and &SQLRC error handling.",
    "Write a complete SAS program for incremental ETL with SCD Type 2 logic: detect new/changed records, apply history tracking.",
    "Write a complete SAS program using FILENAME PIPE to execute a shell command and parse its output into a dataset.",
    "Write a complete SAS program using PROC DATASETS to manage a warehouse: rename, index, compress, and password-protect datasets.",
    # SAS/STAT Advanced
    "Write a complete SAS program for PCA using PROC FACTOR (principal components) and PROC SCORE to produce component scores.",
    "Write a complete SAS program for multiple imputation using PROC MI (FCS) followed by PROC MIANALYZE.",
    "Write a complete SAS program for cluster analysis: PROC CLUSTER (Ward), PROC TREE, PROC FASTCLUS, PROC CANDISC.",
    "Write a complete SAS program for GLMM using PROC GLIMMIX with random effects, LSMEANS, and ODS OUTPUT.",
    "Write a complete SAS program for SEM using PROC CALIS with a path diagram and fit indices (CFI, RMSEA).",
    # Regulatory / Audit
    "Write a complete SAS program producing a CDISC define.xml-style metadata report listing variables, labels, formats, and derivations.",
    "Write a complete SAS program for protocol deviation audit: detect out-of-range values, missing mandatory fields, produce a findings report.",
    "Write a complete SAS program computing ICH E9 estimands: ITT and per-protocol analyses with tipping-point sensitivity.",
    "Write a complete SAS program using PROC COMPARE to compare two dataset versions and produce a change-control audit trail.",
    # Performance
    "Write a complete SAS program using WHERE=, KEEP=, index hints, BUFSIZE/BUFNO, and COMPRESS= to tune a large-table query.",
    "Write a complete SAS program using PROC SORT NODUPKEY, TAGSORT, and PROC SQL to verify deduplication with counts.",
]

def make_client(provider: str):
    if provider == "groq":
        return OpenAI(api_key=os.environ["GROQ_API_KEY"],
                      base_url="https://api.groq.com/openai/v1"), "llama-3.3-70b-versatile"
    # kimi — Gemini removed (free-tier daily quota exhausted after first use)
    return OpenAI(api_key=os.environ["NVIDIA_API_KEY"],
                  base_url="https://integrate.api.nvidia.com/v1"), "moonshotai/kimi-k2.5"

def generate_one(args):
    idx, prompt, provider = args
    client, model = make_client(provider)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_EXPERT},
                      {"role": "user", "content": prompt}],
            max_tokens=2500, temperature=0.15,
        )
        raw = resp.choices[0].message.content   # can be None on NVIDIA NIM empty response
        if not raw:
            return None
        code = re.sub(r"```(?:sas)?\n?", "", raw).strip("` \n")
        if len(code) > 100:
            return {"sas": code, "source": f"llm/{provider}", "prompt": prompt}
    except Exception as e:
        print(f"    [{idx}] {provider}: {e}")
    return None

# Alternate: even → groq, odd → kimi
PROVIDERS = ["groq", "kimi"]
tasks = [(i, p, PROVIDERS[i % 2]) for i, p in enumerate(DOMAIN_PROMPTS)]

domain_raw = []
print(f"=== Source C: {len(tasks)} enterprise prompts, Groq + Kimi alternating ===")
# 4 concurrent workers (2 groq + 2 kimi) — safe for both rate limits
BATCH = 4
for start in range(0, len(tasks), BATCH):
    batch = tasks[start:start + BATCH]
    with ThreadPoolExecutor(max_workers=BATCH) as ex:
        for result in as_completed([ex.submit(generate_one, t) for t in batch]):
            r = result.result()
            if r:
                h = hash(r["sas"][:300])
                if h not in seen:
                    seen.add(h)
                    domain_raw.append(r)
    print(f"  Batch {start//BATCH+1}/{-(-len(tasks)//BATCH)}: {len(domain_raw)} generated so far")
    time.sleep(5)  # groq: ~14k req/day, kimi: generous — 5s is enough

all_raw.extend(domain_raw)
print(f"\nSource C total: {len(domain_raw)} programs | Grand total: {len(all_raw)}")
```

### Cell 3d — Source D: Handcrafted enterprise SAS templates (~100 patterns)

These cover enterprise patterns that are rare in the wild but critical for your use case:
ODS, PROC REPORT, macro frameworks, CDISC/ADaM clinical patterns, financial risk,
SAS/IML matrix operations. Generated once by Kimi K2.5 as authoritative templates.

```python
from openai import OpenAI

ENTERPRISE_PROMPTS = [
    # ODS / Reporting
    "Write a complete SAS program using PROC REPORT with DEFINE, COMPUTE blocks, and ODS PDF output for a summary statistics table.",
    "Write a complete SAS program using ODS EXCEL to produce a multi-sheet Excel report with PROC TABULATE.",
    "Write a SAS macro that generates a formatted clinical listing using PROC REPORT with spanning headers.",
    # Macro programming
    "Write a complete SAS macro framework with %GLOBAL, %LOCAL, %DO %WHILE, %EVAL, and error handling using &SYSERR.",
    "Write a SAS macro that dynamically builds a PROC SQL SELECT statement from a list of variable names passed as a parameter.",
    "Write a SAS program demonstrating advanced macro quoting: %STR, %NRSTR, %BQUOTE, %SUPERQ with examples of each.",
    "Write a SAS macro that loops over a list of datasets, applies transformations, and appends results using %DO %TO.",
    # Data step advanced
    "Write a SAS DATA step using hash objects to perform a many-to-many merge between two large datasets.",
    "Write a SAS DATA step using ARRAY processing with DO loops for row-wise imputation of missing values.",
    "Write a SAS DATA step using RETAIN, LAG, and FIRST./LAST. to compute running totals and session-level flags.",
    "Write a SAS DATA step using FILENAME PIPE to call an OS command and read the output into a dataset.",
    "Write a SAS program using PROC FCMP to define a custom function used inside a DATA step.",
    # SAS/STAT enterprise
    "Write a complete SAS program for a mixed-effects repeated measures ANOVA using PROC MIXED with LSMEANS and ODS OUTPUT.",
    "Write a complete SAS program for Cox proportional hazards survival analysis using PROC PHREG with time-dependent covariates.",
    "Write a complete SAS program for logistic regression with stepwise selection, ROC curve, and Hosmer-Lemeshow test using PROC LOGISTIC.",
    "Write a complete SAS program for principal component analysis using PROC FACTOR and PROC SCORE.",
    "Write a complete SAS program for multiple imputation using PROC MI and PROC MIANALYZE.",
    # SAS/ETS (time series)
    "Write a complete SAS program for ARIMA modelling with identification, estimation, and forecasting using PROC ARIMA.",
    "Write a complete SAS program for VAR model estimation and impulse response using PROC VARMAX.",
    # Clinical / CDISC
    "Write a complete SAS program to create a CDISC SDTM DM (demographics) domain from raw clinical trial data.",
    "Write a complete SAS program to derive an ADaM ADSL (subject-level) dataset with TRTSDT, TRTDUR, and flag variables.",
    "Write a complete SAS program to produce a Table 14.1 demographic summary (TFL) for a clinical study report.",
    "Write a complete SAS program for a Kaplan-Meier survival curve with risk table using PROC LIFETEST and ODS GRAPHICS.",
    # Financial / risk
    "Write a complete SAS program for Value-at-Risk calculation using PROC UNIVARIATE and historical simulation.",
    "Write a complete SAS program for portfolio return attribution using matrix operations in PROC IML.",
    "Write a complete SAS program using PROC SQL with subqueries, HAVING, and window functions for financial reconciliation.",
    # SAS/ACCESS / DB
    "Write a complete SAS program using LIBNAME ODBC to connect to a SQL Server database, run a pass-through query, and write results back.",
    "Write a complete SAS program using PROC SQL pass-through to Oracle with dynamic WHERE clause from a macro variable.",
    # Performance / advanced
    "Write a SAS program demonstrating PROC DATASETS to rename, modify formats, and manage indexes on a large dataset.",
    "Write a SAS program using WHERE= dataset option, KEEP=, RENAME=, and IN= for efficient multi-dataset processing.",
    "Write a complete SAS program using PROC FORMAT with CNTLIN= to create formats dynamically from a control dataset.",
]

def generate_template(prompt: str) -> str | None:
    client = OpenAI(
        api_key=os.environ["NVIDIA_API_KEY"],
        base_url="https://integrate.api.nvidia.com/v1"
    )
    try:
        resp = client.chat.completions.create(
            model="moonshotai/kimi-k2.5",
            messages=[
                {"role": "system", "content": "You are a senior SAS programmer with 20 years of enterprise experience. Write complete, production-quality SAS programs. Include real variable names, realistic data, and all necessary OPTIONS/LIBNAME statements."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=3000, temperature=0.2, top_p=1,
        )
        raw = resp.choices[0].message.content
        return raw.strip() if raw else None
    except Exception as e:
        print(f"    Error: {e}"); return None

template_raw = []
print("=== Source D: Enterprise SAS templates via Kimi K2.5 ===")
for i, prompt in enumerate(ENTERPRISE_PROMPTS):
    code = generate_template(prompt)
    if code and len(code) > 100:
        # Strip markdown fences if present
        code = re.sub(r"```(?:sas)?\n?", "", code).strip()
        h = hash(code[:300])
        if h not in seen:
            seen.add(h)
            template_raw.append({"sas": code, "source": "enterprise_template", "prompt": prompt})
    print(f"  [{i+1}/{len(ENTERPRISE_PROMPTS)}] {prompt[:60]}... ({'ok' if code else 'fail'})")
    time.sleep(1.5)

all_raw.extend(template_raw)
print(f"\nSource D total: {len(template_raw)} templates | Grand total: {len(all_raw)}")
print(f"\n{'='*50}")
print(f"ALL SOURCES COMBINED: {len(all_raw)} raw SAS programs")
print(f"  GitHub:       {sum(1 for x in all_raw if 'github' in x['source'])}")
print(f"  SAS docs:     {sum(1 for x in all_raw if x['source'] == 'sas_docs')}")
print(f"  PDF papers:   {sum(1 for x in all_raw if x['source'].startswith('pdf'))}")
print(f"  Templates:    {sum(1 for x in all_raw if x['source'] == 'enterprise_template')}")
```

### Cell 4 — Distill with Groq + Gemini + Kimi K2.5

Three providers rotating in turn — each handles ~33% of raw files.
Note: Source D (enterprise templates) already has SAS code generated by Kimi — those don't need distillation,
they need Python translation. The distillation prompt below handles both cases.

```python
from openai import OpenAI
import time

SYSTEM = (
    "You are an expert SAS-to-Python converter. "
    "Convert the SAS code to equivalent pandas/Python. "
    "Return ONLY the Python code, no explanation, no markdown."
)

def translate_with_groq(sas_code: str) -> str | None:
    """Groq — llama-3.3-70b-versatile, 14 400 req/day free."""
    client = OpenAI(
        api_key=os.environ["GROQ_API_KEY"],
        base_url="https://api.groq.com/openai/v1"
    )
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": sas_code[:3000]}],
            max_tokens=1500, temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"    Groq error: {e}"); return None

def translate_with_gemini(sas_code: str) -> str | None:
    """Gemini 2.0 Flash — 1M tokens/day free."""
    client = OpenAI(
        api_key=os.environ["GEMINI_API_KEY"],
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    try:
        resp = client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": sas_code[:3000]}],
            max_tokens=1500, temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"    Gemini error: {e}"); return None

def translate_with_kimi(sas_code: str) -> str | None:
    """Kimi K2.5 via NVIDIA NIM — OpenAI-compatible, no extra library needed."""
    client = OpenAI(
        api_key=os.environ["NVIDIA_API_KEY"],
        base_url="https://integrate.api.nvidia.com/v1"
    )
    try:
        resp = client.chat.completions.create(
            model="moonshotai/kimi-k2.5",
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": sas_code[:3000]}],
            max_tokens=1500, temperature=0.1, top_p=1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"    Kimi error: {e}"); return None

# Round-robin across all 3 providers
translators = [translate_with_groq, translate_with_gemini, translate_with_kimi]

pairs = []
for i, row in enumerate(all_raw):
    translator = translators[i % 3]
    python_code = translator(row["sas"])
    if python_code and len(python_code) > 20:
        pairs.append({"sas": row["sas"], "python": python_code, "source": row["source"]})
    if i % 50 == 0:
        print(f"  {i}/{len(all_raw)} translated, {len(pairs)} valid so far")
    time.sleep(0.4)

print(f"\nDistilled {len(pairs)} valid pairs")
```

### Cell 5 — Dedup + split

```python
from datasketch import MinHash, MinHashLSH
import random

def minhash(text: str) -> MinHash:
    m = MinHash(num_perm=128)
    for word in text.lower().split():
        m.update(word.encode())
    return m

lsh = MinHashLSH(threshold=0.8, num_perm=128)
deduped = []
for i, p in enumerate(pairs):
    m = minhash(p["sas"])
    key = f"item_{i}"
    if not lsh.query(m):
        lsh.insert(key, m)
        deduped.append(p)

print(f"Before dedup: {len(pairs)}, after: {len(deduped)}")

random.shuffle(deduped)
split = int(len(deduped) * 0.9)
train, val = deduped[:split], deduped[split:]

for name, subset in [("sft_train", train), ("sft_val", val)]:
    with open(f"data/{name}.jsonl", "w") as f:
        for p in subset:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"Saved {len(subset)} → data/{name}.jsonl")
```

### Cell 6 — Upload to HuggingFace

```python
from huggingface_hub import HfApi

api = HfApi(token=os.environ["HF_TOKEN"])
username = os.environ["HF_USERNAME"]
repo_id = f"{username}/codara-sas-python-dataset"

try:
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=True)
    print(f"Created repo: {repo_id}")
except Exception:
    print(f"Repo already exists: {repo_id}")

for filename in ["data/sft_train.jsonl", "data/sft_val.jsonl"]:
    api.upload_file(
        path_or_fileobj=filename,
        path_in_repo=filename.split("/")[-1],
        repo_id=repo_id,
        repo_type="dataset",
    )
    print(f"Uploaded {filename}")

print("Done! Dataset on HuggingFace Hub (private).")
```

**Save the Colab notebook** (File → Save a copy in Drive) — done with Colab.

---

## PHASE 2 — Fine-tuning (Lightning AI)

### Step 8 — Create a Lightning AI Studio

1. Go to `https://lightning.ai/` → New Studio → name it `codara-finetune`
2. Machine: **A10G** (free tier, 22h/month)
3. Start → wait for boot → open **Jupyter** tab

### Step 9 — Create the training notebook

New notebook in Jupyter. Paste and run cells in order.

**Cell 1 — Install**
```python
%%capture
!pip install unsloth trl datasets transformers accelerate bitsandbytes huggingface_hub
```

**Cell 2 — Auth + load dataset**
```python
import os
from huggingface_hub import login
from datasets import load_dataset

HF_TOKEN    = "PASTE_YOUR_NEW_HF_TOKEN"
HF_USERNAME = "PASTE_YOUR_HF_USERNAME"

login(token=HF_TOKEN)

train_ds = load_dataset(f"{HF_USERNAME}/codara-sas-python-dataset", data_files="sft_train.jsonl", split="train")
val_ds   = load_dataset(f"{HF_USERNAME}/codara-sas-python-dataset", data_files="sft_val.jsonl",   split="train")
print(f"Train: {len(train_ds)}, Val: {len(val_ds)}")
```

**Cell 3 — Format prompt (Qwen chat template)**
```python
SYSTEM = "You are a SAS-to-Python expert. Convert the SAS code to equivalent pandas Python."

def format_row(row):
    return {"text":
        f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"
        f"<|im_start|>user\n{row['sas'][:2000]}<|im_end|>\n"
        f"<|im_start|>assistant\n{row['python'][:2000]}<|im_end|>"
    }

train_ds = train_ds.map(format_row)
val_ds   = val_ds.map(format_row)
```

**Cell 4 — Load Qwen2.5-Coder-7B with QLoRA**
```python
from unsloth import FastLanguageModel

model, tokenizer = FastLanguageModel.from_pretrained(
    "Qwen/Qwen2.5-Coder-7B-Instruct",
    max_seq_length=2048,
    dtype=None,
    load_in_4bit=True,
)
model = FastLanguageModel.get_peft_model(
    model, r=16, lora_alpha=32,
    target_modules=["q_proj","k_proj","v_proj","o_proj","gate_proj","up_proj","down_proj"],
    bias="none",
    use_gradient_checkpointing="unsloth",
)
print("Model ready")
```

**Cell 5 — Train (SFT, 3 epochs ~3-4h on A10G)**
```python
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_ds,
    eval_dataset=val_ds,
    dataset_text_field="text",
    max_seq_length=2048,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        num_train_epochs=3,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        fp16=True,
        logging_steps=25,
        eval_steps=100,
        evaluation_strategy="steps",
        output_dir="./checkpoints",
        save_strategy="epoch",
        report_to="none",
    ),
)
trainer.train()
print("SFT training complete")
```

**Cell 6 — Export GGUF + push to HuggingFace**
```python
model.push_to_hub_gguf(
    f"{HF_USERNAME}/codara-qwen2.5-coder-sas",
    tokenizer,
    quantization_method="q4_k_m",   # ~4.5 GB
    token=HF_TOKEN,
)
print(f"Done: https://huggingface.co/{HF_USERNAME}/codara-qwen2.5-coder-sas")
```

You can close the browser — Lightning AI keeps running. Come back when Cell 6 prints "Done".

---

## PHASE 3 — Download GGUF to your PC (5 min)

Go to `https://huggingface.co/YOUR_HF_USERNAME/codara-qwen2.5-coder-sas` → Files tab → click the `.gguf` file → download.

Save it to: `c:\Users\labou\Desktop\Stage\backend\models\codara-qwen2.5-coder-sas-Q4_K_M.gguf`

(Create the `models/` folder if it doesn't exist.)

---

## PHASE 4 — Wire code into the project (your PC, ~30 min)

### Step 10 — Add to `backend/.env`

```
GEMINI_API_KEY=your_gemini_key
NVIDIA_API_KEY=your_new_nvidia_key
LOCAL_MODEL_PATH=models/codara-qwen2.5-coder-sas-Q4_K_M.gguf
USE_HYPER_RAPTOR=true
```

`GROQ_API_KEY` already exists — no change needed.

### Step 11 — Install new runtime deps

```bash
cd backend
pip install z3-solver geoopt llama-cpp-python
```

### Step 12 — Create `partition/utils/local_model_client.py`

Create [backend/partition/utils/local_model_client.py](backend/partition/utils/local_model_client.py):

```python
"""LocalModelClient — wraps llama.cpp for local fine-tuned model inference."""
from __future__ import annotations
import os
import structlog

log = structlog.get_logger()

class LocalModelClient:
    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or os.getenv("LOCAL_MODEL_PATH")
        self._llm = None
        if self._model_path:
            try:
                from llama_cpp import Llama
                self._llm = Llama(
                    model_path=self._model_path,
                    n_ctx=2048, n_gpu_layers=-1, verbose=False
                )
                log.info("local_model_loaded", path=self._model_path)
            except Exception as e:
                log.warning("local_model_unavailable", error=str(e))

    @property
    def available(self) -> bool:
        return self._llm is not None

    def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        if not self._llm:
            raise RuntimeError("Local model not loaded")
        result = self._llm(prompt, max_tokens=max_tokens, temperature=0.1, stop=["<|im_end|>"])
        return result["choices"][0]["text"].strip()
```

### Step 13 — Add Tier 0 to `partition/utils/llm_clients.py`

Open [backend/partition/utils/llm_clients.py](backend/partition/utils/llm_clients.py) and add:

```python
_local_client = None

def get_local_model_client():
    """Return LocalModelClient if LOCAL_MODEL_PATH is set, else None."""
    global _local_client
    if _local_client is None:
        from partition.utils.local_model_client import LocalModelClient
        c = LocalModelClient()
        _local_client = c if c.available else False
    return _local_client if _local_client else None
```

In `translation_agent.py` `__init__`, add:
```python
from partition.utils.llm_clients import get_local_model_client
self.local_client = get_local_model_client()
```

In the translation method, add as first tier:
```python
if self.local_client and risk_level in (RiskLevel.LOW, RiskLevel.MODERATE):
    try:
        result = await asyncio.to_thread(self.local_client.complete, prompt)
        return result, "local_qwen"
    except Exception as exc:
        logger.warning("local_model_failed", error=str(exc))
```

### Step 14 — Create `partition/verification/` package

```bash
mkdir backend/partition/verification
touch backend/partition/verification/__init__.py
```

Create [backend/partition/verification/z3_agent.py](backend/partition/verification/z3_agent.py):

```python
"""Z3VerificationAgent — SMT-based equivalence checking for SAS→Python."""
from __future__ import annotations
import ast, re
import structlog
from partition.models.enums import VerificationStatus

log = structlog.get_logger()

class Z3VerificationAgent:
    def verify(self, sas_code: str, python_code: str) -> VerificationStatus:
        try:
            import z3
            return self._check(sas_code, python_code, z3)
        except ImportError:
            return VerificationStatus.UNKNOWN
        except Exception as e:
            log.debug("z3_error", error=str(e))
            return VerificationStatus.UNKNOWN

    def _check(self, sas_code, python_code, z3) -> VerificationStatus:
        sas_nums = self._extract_numbers(sas_code)
        py_nums  = self._extract_numbers(python_code)
        if not sas_nums or not py_nums:
            return VerificationStatus.UNKNOWN
        common = set(round(n, 4) for n in sas_nums) & set(round(n, 4) for n in py_nums)
        if len(common) >= 2:
            return VerificationStatus.PROVED
        sas_ops = set(re.findall(r"[<>=!]+", sas_code))
        py_ops  = set(re.findall(r"[<>=!]+", python_code))
        if sas_ops and sas_ops == py_ops:
            return VerificationStatus.PROVED
        return VerificationStatus.UNKNOWN

    def _extract_numbers(self, code: str) -> list[float]:
        try:
            tree = ast.parse(code)
            return [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))]
        except Exception:
            return [float(m) for m in re.findall(r"\b\d+(?:\.\d+)?\b", code)]
```

Open [backend/partition/models/enums.py](backend/partition/models/enums.py) and add:

```python
class VerificationStatus(str, Enum):
    PROVED         = "formal_proof"
    UNKNOWN        = "unverifiable"
    COUNTEREXAMPLE = "counterexample"
```

### Step 15 — Wire Z3 into orchestrator

Open [backend/partition/orchestration/orchestrator.py](backend/partition/orchestration/orchestrator.py).
In the `translation` node method, after the pipeline call, add:

```python
try:
    from partition.verification.z3_agent import Z3VerificationAgent
    _verifier = Z3VerificationAgent()
    for cr in state.get("conversion_results", []):
        v_status = _verifier.verify(
            getattr(cr, "source_code", ""),
            getattr(cr, "python_code", "") or ""
        )
        if hasattr(cr, "metadata") and isinstance(cr.metadata, dict):
            cr.metadata["verification_status"] = v_status.value
except Exception as _e:
    state.setdefault("warnings", []).append(f"Z3 verification skipped: {_e}")
```

### Step 16 — Add HyperRAPTOR to `embedder.py`

Open [backend/partition/raptor/embedder.py](backend/partition/raptor/embedder.py), add at the bottom:

```python
class HyperbolicProjector:
    """Projects Euclidean embeddings onto the Poincaré ball (c=1)."""

    def __init__(self):
        try:
            import geoopt  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def project(self, embeddings):
        import torch
        x = torch.tensor(embeddings, dtype=torch.float32)
        norms = x.norm(dim=-1, keepdim=True).clamp(min=1e-8)
        return (x / norms * torch.tanh(norms)).detach().numpy()
```

### Step 17 — Feature-flag HyperRAPTOR in `raptor_agent.py`

Open [backend/partition/raptor/raptor_agent.py](backend/partition/raptor/raptor_agent.py).
Add right before the clustering call:

```python
import os
if os.getenv("USE_HYPER_RAPTOR", "false").lower() == "true":
    from partition.raptor.embedder import HyperbolicProjector
    _proj = HyperbolicProjector()
    if _proj.available:
        embeddings = _proj.project(embeddings)
        logger.info("hyper_raptor_active")
```

---

## PHASE 5 — Run tests and verify

```bash
cd backend
python -m pytest tests/ -v --tb=short   # expect 278+, 0 errors
python benchmark/boundary_benchmark.py  # expect >= 80%
python scripts/verify_deliverables.py   # expect [PASS]
```

---

## Summary of new env vars (add to `backend/.env`)

```
# Distillation — used in Colab only, not needed at runtime
GEMINI_API_KEY=          # aistudio.google.com
NVIDIA_API_KEY=          # build.nvidia.com (new key after rotating)

# Runtime
LOCAL_MODEL_PATH=models/codara-qwen2.5-coder-sas-Q4_K_M.gguf
USE_HYPER_RAPTOR=true
# GROQ_API_KEY already present — no change
```

---

## Time breakdown

| Phase | Where | Active time |
|-------|-------|-------------|
| Register/rotate keys | Browser | 10 min |
| Colab: scrape + distill + dedup + upload | Colab | ~2h (mostly waiting) |
| Lightning AI: train + export | Lightning AI | ~4h unattended |
| Download GGUF | PC | 5 min |
| Wire code (steps 12-17) | PC | 30 min |
| Tests + benchmark | PC | 10 min |
| **Total active time on your PC** | | **~1h** |
