"""Translation service — SAS→Python LLM translation logic.

Extracted from api.routes.conversions to keep route handlers free of LLM client code.
Fallback chain: Nemotron (Ollama) → Azure OpenAI → Groq (key rotation).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_log = logging.getLogger("codara.translate")

# ── SAS conversion rules (system prompt) ─────────────────────────────────────

_SAS_CONVERSION_RULES = """
## SAS-to-Python Conversion Rules (MANDATORY)

### 1. LIBNAME References — Dot Notation
- `LIBNAME staging '/path/to/dir';` → IGNORE the LIBNAME declaration itself (no Python equivalent).
- When SAS references `libname.dataset` (e.g., `staging.merged`, `work.output`),
  ONLY use the part AFTER the dot as the DataFrame name.
  - `staging.merged` → `merged` (pandas DataFrame)
  - `work.temp_data` → `temp_data`
  - `sashelp.class` → `class_df` (add `_df` suffix to avoid Python keyword conflicts)
- Never create a variable or object named after the libname itself.

### 2. No-Op SAS Statements → `pass` or omit entirely
These SAS statements have NO Python equivalent. Convert them to a `pass` comment or omit:
- `TITLE` / `TITLE1` / `TITLE2` ... → `# TITLE: <original text>` (comment only)
- `FOOTNOTE` / `FOOTNOTE1` ... → `# FOOTNOTE: <original text>`
- `OPTIONS` (e.g., `OPTIONS NOCENTER NODATE;`) → `# SAS OPTIONS: <ignored>`
- `GOPTIONS` → `# SAS GOPTIONS: <ignored>`
- `ODS` statements (e.g., `ODS HTML`, `ODS LISTING CLOSE`) → `# ODS: <ignored>`
- `DM` (display manager commands) → omit
- `%SYSEXEC` → omit (or `os.system()` if truly needed)
- `ENDSAS;` → omit
- `RUN;` → omit (implicit in Python)
- `QUIT;` → omit

### 3. Variable Naming
- SAS variables are case-insensitive. Python is case-sensitive.
  → Use lowercase_snake_case for all variable names.
- If a SAS variable name is a Python keyword (e.g., `class`, `type`, `input`, `format`),
  append `_col` or `_var` → `class_col`, `type_var`, `input_col`.

### 4. Missing Values
- SAS missing numeric = `.` → Python `np.nan` / `pd.NA`
- SAS missing char = `' '` (blank) → Python `None` or `''`
- SAS comparison with missing: `. < 0` is TRUE in SAS → Use `pd.isna()` checks.
- `NMISS()` → `.isna().sum()`
- `CMISS()` → `.isna().sum()`

### 5. SAS Date Handling
- SAS dates are days since Jan 1, 1960.
- Do NOT manually offset by 3653 days — pandas handles epochs.
- `TODAY()` → `pd.Timestamp.today().normalize()`
- `MDY(m, d, y)` → `pd.Timestamp(year=y, month=m, day=d)`
- `INTNX('MONTH', date, n)` → `date + pd.DateOffset(months=n)`
- `INTCK('DAY', d1, d2)` → `(d2 - d1).days`
- `DATEPART(datetime)` → `datetime.normalize()` or `.dt.date`

### 6. DATA Step → pandas
- `DATA output; SET input;` → `output = input.copy()`
- `DATA output; SET input; WHERE condition;` → `output = input[condition].copy()`
- `DATA output; MERGE a b; BY key;` → `output = pd.merge(a, b, on='key', how='outer')`
- `RETAIN var init;` → Use `.cumsum()`, `.expanding()`, or explicit loop
- `FIRST.var / LAST.var` → Use `groupby().cumcount()` flags
- `OUTPUT;` → `rows.append(...)` then `pd.DataFrame(rows)`
- `IF ... THEN DELETE;` → `df = df[~condition]`
- `LENGTH var $50;` → `df['var'] = df['var'].astype(str)`

### 7. PROC Statements → pandas equivalents
- `PROC SORT DATA=ds; BY var;` → `ds = ds.sort_values('var')`
- `PROC SORT NODUPKEY;` → `ds = ds.drop_duplicates(subset=['var'])`
- `PROC MEANS` → `df.describe()` or `df.groupby().agg()`
- `PROC FREQ` → `pd.crosstab()` or `df['col'].value_counts()`
- `PROC PRINT` → `print(df)` or `df.head()`
- `PROC SQL; SELECT ... FROM ... ;` → `pd.read_sql()` or direct pandas operations
- `PROC TRANSPOSE` → `df.pivot()` / `df.melt()`
- `PROC EXPORT` → `df.to_csv()` / `df.to_excel()`
- `PROC IMPORT` → `pd.read_csv()` / `pd.read_excel()`
- `PROC CONTENTS` → `df.info()` / `df.dtypes`
- `PROC REG` → `from sklearn.linear_model import LinearRegression`
- `PROC LOGISTIC` → `from sklearn.linear_model import LogisticRegression`

### 8. Macro Variables
- `%LET var = value;` → `var = 'value'` (or appropriate type)
- `&var` / `&var.` references → Use the Python variable directly (f-string if in text)
- `%MACRO name(...); ... %MEND;` → `def name(...):` — ONLY if the macro is called more than once.
  If called once, expand it inline as top-level statements (no `def`).
- `%IF ... %THEN ... %ELSE ...` → standard Python `if/else`
- `%DO ... %END` → `for` loop
- `%INCLUDE 'file.sas';` → `exec(open('file.py').read())` or `import module`

### 12. NO Unnecessary `def` Functions
- **Script-level SAS code MUST translate to top-level Python statements** — NOT wrapped in `def main()`,
  `def run()`, `def process()`, or any function. SAS is a script; Python output must also be a script.
- **For IF/ELIF value-mapping chains** (enum code → label), use a dict + `.map()`:
    WRONG: `def map_status(v): if v=='1': return 'Active'; ...` then `df['col'].apply(map_status)`
    RIGHT: `df['status'] = df['STATUS'].map({'1': 'Active', '2': 'Inactive'}).fillna('ERREUR')`
- **For numeric range binning**, use `np.select()` or `pd.cut()`:
    WRONG: `def categorize(v): if v <= 1000: return '[>0;1000]'; ...` then `.apply(categorize)`
    RIGHT: `df['cat'] = np.select([df['v']<=1000, df['v']<=7000], ['[>0;1000]','[>1000;7000]'], default='ERREUR')`
         — or: `df['cat'] = pd.cut(df['v'], bins=[0,1000,7000,float('inf')], labels=['[>0;1000]','[>1000;7000]','>7000'], right=True)`
- **`def` is ONLY correct for** a `%MACRO` called 2+ times. Everything else: top-level statements.

### 9. SAS Functions → Python/pandas
- `INPUT(var, numfmt.)` → `pd.to_numeric(var)`
- `PUT(var, charfmt.)` → `str(var)` or `.astype(str)`
- `SUBSTR(str, pos, len)` → `str[pos-1:pos-1+len]` (SAS is 1-indexed!)
- `SCAN(str, n, delim)` → `str.split(delim)[n-1]`
- `COMPRESS(str)` → `str.replace(' ', '')`
- `STRIP(str)` / `TRIM(str)` → `str.strip()`
- `UPCASE(str)` → `str.upper()`
- `LOWCASE(str)` → `str.lower()`
- `PROPCASE(str)` → `str.title()`
- `CATX(delim, ...)` → `delim.join([...])`
- `CATS(...)` → `''.join([str(x).strip() for x in [...]])`
- `SUM(a, b, ...)` → `np.nansum([a, b, ...])` (SAS SUM ignores missing!)
- `MEAN(a, b)` → `np.nanmean([a, b])`
- `MIN(a, b)` / `MAX(a, b)` → `np.nanmin()` / `np.nanmax()`
- `LAG(var)` → `df['var'].shift(1)`
- `LAG2(var)` → `df['var'].shift(2)`
- `ABS(x)` → `abs(x)`
- `ROUND(x, r)` → `round(x, -int(np.log10(r)))` or custom
- `INT(x)` → `int(x)` or `np.floor(x)`
- `LOG(x)` → `np.log(x)`
- `EXP(x)` → `np.exp(x)`

### 10. SAS Formats & Informats → Ignore or Comment
- `FORMAT var date9.;` → `# FORMAT: date9. applied to var`
- `INFORMAT var ...;` → Ignore (informats are read-time only)
- `LABEL var = 'description';` → `# LABEL: var = 'description'` (comment only)
- `ATTRIB` statements → comment only

### 11. Output Delivery
- `PROC EXPORT DATA=ds OUTFILE='file.csv' DBMS=CSV;` → `ds.to_csv('file.csv', index=False)`
- `FILE 'output.txt';` / `PUT ...;` → `with open('output.txt', 'w') as f: f.write(...)`
"""


def _strip_markdown_fences(code: str) -> str:
    """Remove markdown code fences if the LLM wraps the output."""
    code = code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        lines = lines[1:]  # remove opening fence line
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)
    return code


def translate_sas_to_python(sas_code: str) -> str:
    """Translate SAS code to Python via Nemotron (primary) with Azure/Groq fallbacks.

    Uses the PromptManager Jinja2 templates when available, falls back to the
    comprehensive rules-based system prompt otherwise.
    Returns translated Python code, or a stub comment if no LLM is configured.

    Fallback chain: Nemotron (Ollama) → Azure OpenAI → Groq (key rotation) → stub.
    """
    from config.constants import (
        AZURE_MAX_COMPLETION_TOKENS,
        GROQ_MAX_TOKENS,
        LLM_TRANSLATION_TEMPERATURE,
    )
    from config.settings import settings

    # Ensure backend package is on sys.path for partition imports
    pkg_root = str(Path(__file__).resolve().parent.parent.parent.parent)
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)

    # Detect failure modes for smarter prompts
    failure_guidance = ""
    try:
        from partition.translation.failure_mode_detector import (
            detect_failure_mode,
            get_failure_mode_rules,
        )

        fm = detect_failure_mode(sas_code)
        if fm:
            failure_guidance = get_failure_mode_rules(fm)
    except Exception:
        pass

    target_label = "Python (pandas)"

    # Try to use the PromptManager with Jinja2 templates
    rendered_prompt = None
    try:
        from partition.prompts import PromptManager

        pm = PromptManager()
        rendered_prompt = pm.render(
            "translation_static",
            target_label=target_label,
            partition_type="FULL_FILE",
            risk_level="MODERATE",
            complexity=0.5,
            sas_code=sas_code,
            failure_mode_rules=failure_guidance,
            kb_examples=[],
        )
    except Exception:
        pass

    system_prompt = (
        f"You are an expert SAS-to-{target_label} code translator.\n\n"
        f"{_SAS_CONVERSION_RULES}\n\n"
        "Return ONLY the Python code. No explanations, no markdown fences, no commentary.\n\n"
        "CRITICAL RULES:\n"
        "- You MUST translate EVERY section, macro, data step, and proc in the SAS code.\n"
        "- NEVER use placeholders like '# ... (rest of the code remains the same)' or '# TODO'.\n"
        "- NEVER skip, abbreviate, or summarize any part of the code.\n"
        "- If the SAS code has 14 sections, your Python output MUST have all 14 sections fully implemented.\n"
        "- DO NOT wrap output in `def main()`, `def run()`, or any function — produce a flat script.\n"
        "- DO NOT use `def` helper functions for IF/ELIF value-mapping; use dict+`.map()` or `np.select()` instead.\n"
        "- `def` is ONLY acceptable when translating a `%MACRO` that is called more than once.\n"
        "- Translate ALL macros to Python functions with complete logic (only if called 2+ times; otherwise inline).\n"
        "- Translate ALL PROC SQL to pandas operations or raw SQL equivalents.\n"
        "- Translate ALL DATA steps to pandas DataFrame operations.\n"
        "- The output must be a complete, runnable Python script — no stubs, no omissions."
    )

    if failure_guidance:
        system_prompt += f"\n\n## Detected Failure Mode\n{failure_guidance}"

    user_prompt = rendered_prompt or (
        f"Convert this SAS code to {target_label}:\n```sas\n{sas_code}\n```"
    )

    # --- Try Nemotron via Ollama (primary) ---
    if settings.ollama_base_url:
        try:
            from openai import OpenAI

            nem_client = OpenAI(
                api_key=settings.ollama_api_key or "ollama",
                base_url=settings.ollama_base_url,
            )
            resp = nem_client.chat.completions.create(
                model="nemotron-3-super:cloud",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=LLM_TRANSLATION_TEMPERATURE,
                max_tokens=AZURE_MAX_COMPLETION_TOKENS,
            )
            code = resp.choices[0].message.content or ""
            return _strip_markdown_fences(code).strip()
        except Exception as exc:
            _log.warning("nemotron_failed type=%s error=%s", type(exc).__name__, exc)

    # --- Try Azure OpenAI (fallback 1) ---
    azure_key = settings.azure_openai_api_key
    azure_endpoint = settings.azure_openai_endpoint
    if azure_key and azure_endpoint:
        try:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                azure_endpoint=azure_endpoint,
                api_key=azure_key,
                api_version=settings.azure_openai_api_version,
            )
            resp = client.chat.completions.create(
                model=settings.azure_openai_deployment_mini,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=LLM_TRANSLATION_TEMPERATURE,
                max_completion_tokens=AZURE_MAX_COMPLETION_TOKENS,
            )
            code = resp.choices[0].message.content or ""
            return _strip_markdown_fences(code).strip()
        except Exception as exc:
            _log.warning("azure_openai_failed type=%s error=%s", type(exc).__name__, exc)

    # --- Try Groq (fallback 2, key rotation: GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3) ---
    try:
        from partition.utils.llm_clients import get_all_groq_keys

        groq_keys = get_all_groq_keys()
    except Exception:
        groq_keys = [
            k
            for k in [
                settings.groq_api_key,
                settings.groq_api_key_2,
                settings.groq_api_key_3,
            ]
            if k
        ]

    last_groq_exc = None
    for groq_key in groq_keys:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            resp = client.chat.completions.create(
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=LLM_TRANSLATION_TEMPERATURE,
                max_tokens=GROQ_MAX_TOKENS,
            )
            code = resp.choices[0].message.content or ""
            return _strip_markdown_fences(code).strip()
        except Exception as exc:
            err_str = str(exc).lower()
            if "rate_limit" in err_str or "429" in err_str or "tokens per day" in err_str:
                _log.warning("groq_key_rate_limited error=%s", str(exc)[:120])
                last_groq_exc = exc
                continue
            _log.warning("groq_failed type=%s error=%s", type(exc).__name__, exc)
            last_groq_exc = exc
            break

    if last_groq_exc:
        _log.warning("groq_all_keys_exhausted error=%s", str(last_groq_exc)[:120])

    # --- No LLM available ---
    _log.error("all_llm_providers_failed sas_len=%d", len(sas_code))
    commented = "\n".join(f"# {line}" for line in sas_code.split("\n"))
    return (
        "# TRANSLATION UNAVAILABLE — no LLM API key configured\n"
        "# Configure AZURE_OPENAI_API_KEY or GROQ_API_KEY in .env\n"
        "#\n"
        "# Original SAS code:\n" + commented
    )
