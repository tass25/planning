"""Cross-provider KB benchmark — "Fixed SAS + Provider Comparison" methodology.

Approach (faster and fairer than full 3-prompt chain per provider):
  Step 1 — SAS generation (once, via Groq, fast ~2s/call):
      6 SAS inputs generated → saved to fixed_sas_{run_id}.json

  Step 2 — Python conversion (each provider, only Prompt B):
      Same 6 SAS codes sent to each enabled provider.
      Providers: mistral, kimi, gemini, azure, groq_gen

  Step 3 — Verification (Groq, fast ~1s/call):
      All outputs cross-verified with Groq LLaMA-3.3-70B.

  Step 4 — Tableau:
      Side-by-side table: confidence, latency, lines, issues per provider.

Why this is better:
  - Apples-to-apples: all providers see the SAME SAS code
  - Fast: total runtime ~5 min vs ~46 min for full chain
  - Fair: isolates Python translation quality, removes SAS gen variance

Usage::
    cd backend
    source /c/Users/labou/Desktop/Stage/venv/Scripts/activate
    python scripts/run_benchmark.py
    python scripts/run_benchmark.py --providers mistral gemini groq_gen
    python scripts/run_benchmark.py --fixed-sas knowledge_base/fixed_sas_abc123.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from openai import AzureOpenAI, OpenAI
import instructor
from pydantic import BaseModel, Field

# ── Pydantic models ──────────────────────────────────────────────────────────

class GeneratedSAS(BaseModel):
    sas_code: str = Field(..., description="Realistic SAS code block")
    category: str = Field(..., description="e.g., DATA_STEP_BASIC, PROC_SQL")
    complexity_tier: str = Field(..., description="LOW | MODERATE | HIGH")
    failure_mode: str = Field(default="", description="Injected failure mode or empty")
    description: str = Field(..., description="What this SAS code does")


class ConvertedPython(BaseModel):
    python_code: str = Field(..., description="Python equivalent using pandas")
    imports_needed: list[str] = Field(default_factory=list)
    notes: str = Field(default="", description="Translation notes")


class CrossVerifyResult(BaseModel):
    equivalent: bool
    issues: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)


# ── 6 fixed SAS tasks (diverse, one per category) ───────────────────────────

FIXED_TASKS = [
    {
        "category": "DATA_STEP_RETAIN",
        "complexity": "MODERATE",
        "failure_mode": "RETAIN",
        "constructs": "RETAIN, running totals, lag patterns",
    },
    {
        "category": "DATA_STEP_MERGE",
        "complexity": "MODERATE",
        "failure_mode": "MERGE_SEMANTICS",
        "constructs": "MERGE BY, one-to-many, UPDATE",
    },
    {
        "category": "PROC_SQL",
        "complexity": "MODERATE",
        "failure_mode": "",
        "constructs": "SELECT, JOIN, GROUP BY, HAVING",
    },
    {
        "category": "DATE_ARITHMETIC",
        "complexity": "MODERATE",
        "failure_mode": "DATE_ARITHMETIC",
        "constructs": "MDY, TODAY, INTNX, INTCK, DATEPART",
    },
    {
        "category": "MACRO_BASIC",
        "complexity": "LOW",
        "failure_mode": "",
        "constructs": "%MACRO/%MEND, %LET, macro parameters",
    },
    {
        "category": "PROC_MEANS",
        "complexity": "MODERATE",
        "failure_mode": "PROC_MEANS_OUTPUT",
        "constructs": "CLASS, VAR, OUTPUT OUT=, NWAY",
    },
]

# ── Provider config ──────────────────────────────────────────────────────────

PROVIDERS = {
    "groq_gen": {
        "env_key":       "GROQ_API_KEY",
        "base_url":      "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "is_azure":      False,
        "label":         "Groq LLaMA-3.3-70B",
    },
    "mistral": {
        "env_key":       "NVIDIA_API_KEY_MISTRAL",
        "base_url":      "https://integrate.api.nvidia.com/v1",
        "default_model": "mistralai/mistral-medium-3-instruct",
        "is_azure":      False,
        "label":         "Mistral Medium 3 (NVIDIA NIM)",
    },
    "kimi": {
        "env_key":       "NVIDIA_API_KEY_MISTRAL",
        "base_url":      "https://integrate.api.nvidia.com/v1",
        "default_model": "moonshotai/kimi-k2-instruct",
        "is_azure":      False,
        "label":         "Kimi K2 (NVIDIA NIM)",
    },
    "gemini": {
        "env_key":       "GEMINI_API_KEY",
        "base_url":      "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
        "is_azure":      False,
        "label":         "Gemini 2.0 Flash",
    },
    "azure": {
        "env_key":       "AZURE_OPENAI_API_KEY",
        "base_url":      None,
        "default_model": "gpt-4o",
        "is_azure":      True,
        "label":         "Azure GPT-4o",
    },
}

_GROQ_KEYS: list[str] = []
_GROQ_KEY_IDX = 0

_FM_RULES: dict[str, str] = {
    "DATE_ARITHMETIC": (
        "CRITICAL: SAS dates count from 1960-01-01. Use pd.to_datetime(), pd.DateOffset(), "
        "pd.Timedelta(). INTNX('MONTH',d,1) -> d + pd.DateOffset(months=1). "
        "INTCK('DAY',d1,d2) -> (d2-d1).days."
    ),
    "MERGE_SEMANTICS": (
        "CRITICAL: SAS MERGE BY is a zipper join, NOT inner join. Use pd.merge(how='outer') "
        "and forward-fill. Watch for many-to-many Cartesian explosions."
    ),
    "RETAIN": (
        "CRITICAL: SAS RETAIN preserves values across iterations. Use cumsum(), expanding(), "
        "or explicit loops in pandas. Do NOT use shift() as a general replacement."
    ),
    "FIRST_LAST": (
        "CRITICAL: SAS FIRST.var/LAST.var identify group boundaries after PROC SORT. "
        "first_flag = df.groupby('var').cumcount() == 0. "
        "last_flag = df.groupby('var').cumcount(ascending=False) == 0."
    ),
    "MISSING_VALUE_COMPARISON": (
        "CRITICAL: SAS missing numeric is -inf in comparisons. Python NaN is neither < nor > anything. "
        "Use pd.isna() explicitly."
    ),
    "PROC_MEANS_OUTPUT": (
        "CRITICAL: OUTPUT OUT= creates _TYPE_, _FREQ_, stat columns. "
        "Use df.groupby().agg() + reset_index() in pandas."
    ),
}


# Providers that need plain (non-instructor) API calls to avoid rate-limit issues
# with structured output endpoints.
_PLAIN_PROVIDERS = {"gemini"}


# ── Client helpers ────────────────────────────────────────────────────────────

def _make_client(provider_name: str) -> tuple[instructor.Instructor, str]:
    """Build instructor client for a provider. Returns (client, model_name)."""
    cfg = PROVIDERS[provider_name]
    api_key = os.getenv(cfg["env_key"], "")
    if not api_key:
        raise RuntimeError(f"Missing env var: {cfg['env_key']}")

    model = cfg["default_model"]

    if cfg["is_azure"]:
        raw = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
        model = os.getenv("AZURE_OPENAI_DEPLOYMENT_FULL", "gpt-4o")
        client = instructor.from_openai(raw)
    else:
        raw = OpenAI(api_key=api_key, base_url=cfg["base_url"])
        client = instructor.from_openai(raw, mode=instructor.Mode.JSON)

    return client, model


def _convert_plain(sas_item: dict, provider_name: str) -> tuple[dict | None, float, str | None]:
    """Plain (no-instructor) conversion for providers with strict structured-output rate limits.

    Asks the model to return JSON in a ```json block, parses manually.
    Uses 1 API call per pair instead of instructor's 3+ retries.
    Returns (result_dict | None, elapsed_s, error_label | None).
    """
    cfg = PROVIDERS[provider_name]
    api_key = os.getenv(cfg["env_key"], "")
    if not api_key:
        return None, 0.0

    model = cfg["default_model"]
    raw = OpenAI(api_key=api_key, base_url=cfg["base_url"])

    fm = sas_item.get("failure_mode", "")
    fm_rules = _FM_RULES.get(fm, "")

    prompt = (
        f"Convert this SAS code to Python (pandas).\n\n"
        f"SAS Code:\n```sas\n{sas_item['sas_code']}\n```\n\n"
        f"Description: {sas_item.get('description','')}\n\n"
        f"{fm_rules}\n"
        "Requirements:\n"
        "- Valid Python with all necessary imports\n"
        "- Idiomatic pandas patterns\n"
        "- Brief inline comments for non-obvious translations\n\n"
        "Respond ONLY with a JSON object (no markdown, no explanation) in this exact format:\n"
        '{"python_code": "...full python code here...", '
        '"imports_needed": ["pandas", "numpy"], '
        '"notes": "brief notes"}\n'
    )

    t0 = time.perf_counter()
    # Single attempt — on 429 or any error, record and move on immediately.
    # Goal is to document the error in the benchmark tableau, not retry forever.
    try:
        resp = raw.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        text = resp.choices[0].message.content or ""
        # Strip markdown fences if present
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        data = json.loads(text)
        elapsed = round(time.perf_counter() - t0, 2)
        return {
            "python_code": data.get("python_code", ""),
            "imports_needed": data.get("imports_needed", []),
            "notes": data.get("notes", ""),
        }, elapsed, None
    except Exception as exc:
        err = str(exc)
        err_label = _classify_error(err)
        print(f"    plain convert failed: {err[:120]}")
        return None, round(time.perf_counter() - t0, 2), err_label


def _groq_verifier() -> tuple[instructor.Instructor, str]:
    global _GROQ_KEY_IDX
    if not _GROQ_KEYS:
        raise RuntimeError("No Groq keys available for verification")
    key = _GROQ_KEYS[_GROQ_KEY_IDX % len(_GROQ_KEYS)]
    raw = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
    return instructor.from_openai(raw, mode=instructor.Mode.JSON), "llama-3.3-70b-versatile"


def _rotate_groq() -> None:
    global _GROQ_KEY_IDX
    _GROQ_KEY_IDX = (_GROQ_KEY_IDX + 1) % max(len(_GROQ_KEYS), 1)


# ── Step 1: Generate SAS inputs (Groq, once) ─────────────────────────────────

def generate_sas_inputs(run_id: str) -> list[dict]:
    """Generate 6 SAS code blocks using Groq (fast ~2s/call). Return list of dicts."""
    print("\n[Step 1] Generating SAS inputs via Groq (fast, done once) ...")

    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        raise RuntimeError("GROQ_API_KEY required for SAS generation step")

    client = instructor.from_openai(
        OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1"),
        mode=instructor.Mode.JSON,
    )
    model = "llama-3.3-70b-versatile"

    sas_inputs: list[dict] = []
    for i, task in enumerate(FIXED_TASKS, 1):
        fm_note = ""
        if task["failure_mode"]:
            fm_note = f"\nIMPORTANT: The code MUST use the {task['failure_mode']} pattern.\n"

        prompt = (
            f"Generate a realistic SAS code block for category '{task['category']}'.\n"
            f"Constructs: {task['constructs']}\n"
            f"Complexity: {task['complexity']}\n"
            f"{fm_note}"
            "Requirements:\n"
            "- Syntactically valid SAS\n"
            "- Realistic dataset and variable names\n"
            "- Brief inline comments\n"
            "- 20-60 lines\n"
        )

        t0 = time.perf_counter()
        for attempt in range(3):
            try:
                result = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=GeneratedSAS,
                    max_retries=1,
                )
                elapsed = round(time.perf_counter() - t0, 2)
                print(f"  [{i}/6] {task['category']} ({task['complexity']}) — {elapsed}s")
                sas_inputs.append({
                    "task_index":   i - 1,
                    "category":     task["category"],
                    "complexity":   task["complexity"],
                    "failure_mode": task["failure_mode"],
                    "constructs":   task["constructs"],
                    "sas_code":     result.sas_code,
                    "description":  result.description,
                    "generated_by": "groq/llama-3.3-70b-versatile",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                })
                break
            except Exception as exc:
                err = str(exc)
                if "429" in err and attempt < 2:
                    print(f"  [{i}/6] 429 rate limit — waiting 15s ...")
                    time.sleep(15)
                else:
                    print(f"  [{i}/6] FAILED: {err[:120]}")
                    break

    print(f"  Generated {len(sas_inputs)}/6 SAS inputs.")
    return sas_inputs


# ── Step 2: Convert SAS → Python (one provider) ──────────────────────────────

def _classify_error(err: str) -> str:
    """Return a short human-readable error label from an exception string."""
    err_lower = err.lower()
    if "429" in err:
        return "HTTP 429 — rate limit exceeded (free tier quota)"
    if "connection error" in err_lower or "connectionerror" in err_lower:
        return "Connection error — endpoint unreachable (network/VPN/firewall)"
    if "400" in err:
        return "HTTP 400 — JSON schema validation failure"
    if "401" in err or "authentication" in err_lower:
        return "HTTP 401 — authentication failure (bad API key)"
    if "404" in err:
        return "HTTP 404 — deployment/model not found"
    if "504" in err:
        return "HTTP 504 — gateway timeout (NIM server overloaded)"
    if "500" in err or "502" in err or "503" in err:
        return "HTTP 5xx — provider server error"
    if "timeout" in err_lower:
        return "Timeout — response exceeded limit"
    if "failed to generate" in err_lower or "json" in err_lower:
        return "JSON parse failure — model output did not match schema"
    return f"Unknown error: {err[:80]}"


def convert_with_provider(sas_inputs: list[dict], provider_name: str) -> list[dict]:
    """Run Prompt B on each SAS input using the given provider.

    Each result dict carries a 'convert_error' key (None on success, error label on failure)
    so the tableau can document exactly what went wrong per provider.
    """
    cfg = PROVIDERS[provider_name]
    print(f"\n[Step 2] Converting with {cfg['label']} ...")

    # Try to build the client — capture auth/config errors upfront
    provider_error: str | None = None
    client = None
    model = cfg["default_model"]
    try:
        client, model = _make_client(provider_name)
    except RuntimeError as e:
        provider_error = _classify_error(str(e))
        print(f"  SKIP {provider_name}: {provider_error}")

    results: list[dict] = []
    for i, sas_item in enumerate(sas_inputs, 1):

        # If provider-level error (missing key, unreachable), record for every pair
        if provider_error or client is None:
            results.append({
                **sas_item,
                "provider":       provider_name,
                "model":          model,
                "python_code":    None,
                "imports":        [],
                "py_notes":       "",
                "t_convert_s":    0.0,
                "convert_ok":     False,
                "convert_error":  provider_error or "client_init_failed",
            })
            continue

        fm = sas_item.get("failure_mode", "")
        fm_rules = _FM_RULES.get(fm, "")

        prompt = (
            f"Convert this SAS code to Python (pandas).\n\n"
            f"SAS Code:\n```sas\n{sas_item['sas_code']}\n```\n\n"
            f"Description: {sas_item.get('description','')}\n\n"
            f"{fm_rules}\n"
            "Requirements:\n"
            "- Valid Python with all necessary imports\n"
            "- Idiomatic pandas patterns\n"
            "- Brief inline comments for non-obvious translations\n"
        )

        # Plain-mode providers bypass instructor entirely
        if provider_name in _PLAIN_PROVIDERS:
            plain_out, elapsed, plain_err = _convert_plain(sas_item, provider_name)
            print(f"  [{i}/6] {sas_item['category']} — {elapsed}s  {'OK' if plain_out else 'FAILED'}")
            results.append({
                **sas_item,
                "provider":      provider_name,
                "model":         model,
                "python_code":   plain_out["python_code"] if plain_out else None,
                "imports":       plain_out["imports_needed"] if plain_out else [],
                "py_notes":      plain_out["notes"] if plain_out else "",
                "t_convert_s":   elapsed,
                "convert_ok":    plain_out is not None,
                "convert_error": plain_err,
            })
            time.sleep(5)
            continue

        t0 = time.perf_counter()
        py_result = None
        last_error: str | None = None
        for attempt in range(2):
            try:
                py_result = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=ConvertedPython,
                    max_retries=3,
                )
                last_error = None
                break
            except Exception as exc:
                err = str(exc)
                last_error = _classify_error(err)
                if "429" in err:
                    # Document the error immediately — no long waits
                    print(f"  [{i}/6] {provider_name} 429 rate limit — recording error, skipping pair")
                    break
                elif "connection" in err.lower():
                    print(f"  [{i}/6] {provider_name} connection error — recording, skipping provider")
                    break
                elif "400" in err and attempt < 1:
                    print(f"  [{i}/6] {provider_name} 400 (schema) — retrying in 3s ...")
                    time.sleep(3)
                else:
                    print(f"  [{i}/6] {provider_name} FAILED: {last_error}")
                    break

        elapsed = round(time.perf_counter() - t0, 2)
        status = "OK" if py_result else f"FAILED ({last_error})"
        print(f"  [{i}/6] {sas_item['category']} — {elapsed}s  {status}")

        results.append({
            **sas_item,
            "provider":      provider_name,
            "model":         model,
            "python_code":   py_result.python_code if py_result else None,
            "imports":       py_result.imports_needed if py_result else [],
            "py_notes":      py_result.notes if py_result else "",
            "t_convert_s":   elapsed,
            "convert_ok":    py_result is not None,
            "convert_error": last_error,
        })

    return results


# ── Step 3: Verify (Groq) ────────────────────────────────────────────────────

def verify_results(results: list[dict]) -> list[dict]:
    """Run Prompt C on all converted results using Groq."""
    print("\n[Step 3] Cross-verifying with Groq ...")
    verifier, verify_model = _groq_verifier()

    verified: list[dict] = []
    for i, r in enumerate(results, 1):
        if not r.get("convert_ok") or not r.get("python_code"):
            r.update({"confidence": 0.0, "equivalent": False, "issues": ["conversion_failed"],
                       "t_verify_s": 0.0, "verify_model": verify_model})
            verified.append(r)
            continue

        fm = r.get("failure_mode", "")
        fm_check = (
            f"\nPay special attention to the {fm} pattern.\n" if fm else ""
        )
        prompt = (
            "You are a code equivalence verifier.\n\n"
            f"SAS Code:\n```sas\n{r['sas_code']}\n```\n\n"
            f"Python Code:\n```python\n{r['python_code']}\n```\n\n"
            f"{fm_check}"
            "Only flag issues if the specific pattern is PRESENT and INCORRECTLY handled.\n"
            "Return structured JSON.\n"
        )

        t0 = time.perf_counter()
        verify = None
        for attempt in range(3):
            try:
                verify = verifier.chat.completions.create(
                    model=verify_model,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=CrossVerifyResult,
                    max_retries=1,
                )
                break
            except Exception as exc:
                err = str(exc)
                if "429" in err and attempt < 2:
                    _rotate_groq()
                    verifier, verify_model = _groq_verifier()
                    print(f"  [{i}] Groq 429 rotated key, retrying ...")
                    time.sleep(10)
                else:
                    print(f"  [{i}] verify FAILED: {err[:100]}")
                    break

        t_verify = round(time.perf_counter() - t0, 2)
        conf = verify.confidence if verify else 0.0
        print(f"  [{i}/{ len(results)}] {r['category']} ({r['provider']}) conf={conf:.2f}  {t_verify}s")

        r.update({
            "confidence":    conf,
            "equivalent":    verify.equivalent if verify else False,
            "issues":        verify.issues if verify else ["verify_failed"],
            "t_verify_s":    t_verify,
            "verify_model":  verify_model,
        })
        verified.append(r)

    return verified


# ── Step 4: Print tableau récapitulatif ──────────────────────────────────────

def print_tableau(all_results: list[dict], run_id: str, providers_used: list[str]) -> None:
    """Print the complete benchmark comparison table."""

    def p(line: str = "") -> None:
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="replace").decode())

    p()
    p("=" * 120)
    p("  TABLEAU RECAPITULATIF — BENCHMARK MULTI-PROVIDER KB GENERATION")
    p(f"  Run ID: {run_id}  |  Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    p(f"  Methodology: Fixed SAS inputs (Groq) + Provider-specific Python conversion")
    p(f"  Providers compared: {', '.join(providers_used)}")
    p("=" * 120)

    # ── A. Per-provider summary ──────────────────────────────────────────────
    p("\n[A] PROVIDER SUMMARY")
    p("-" * 120)
    p(f"{'Provider':<12} {'Model':<45} {'Pairs':>6} {'OK':>4} {'Acc%':>5} {'AvgConf':>8} {'MinConf':>8} {'AvgConvt':>10} {'AvgVerif':>9}")
    p("-" * 120)

    for prov in providers_used:
        rows = [r for r in all_results if r.get("provider") == prov]
        if not rows:
            continue
        ok = [r for r in rows if r.get("convert_ok")]
        failed = [r for r in rows if not r.get("convert_ok")]
        confs = [r["confidence"] for r in rows if r.get("confidence", 0) > 0]
        conv_times = [r["t_convert_s"] for r in ok]
        verify_times = [r.get("t_verify_s", 0) for r in rows]
        model = rows[0].get("model", "?")
        p(
            f"{prov:<12} "
            f"{model:<45} "
            f"{len(rows):>6} "
            f"{len(ok):>4} "
            f"{len(ok)/max(len(rows),1)*100:>4.0f}% "
            f"{sum(confs)/max(len(confs),1):>8.3f} "
            f"{min(confs) if confs else 0:>8.3f} "
            f"{sum(conv_times)/max(len(conv_times),1):>9.1f}s "
            f"{sum(verify_times)/max(len(verify_times),1):>8.2f}s"
        )
        # Show failure reason if any pairs failed
        if failed:
            # Collect distinct error labels
            error_labels: dict[str, int] = {}
            for r in failed:
                lbl = r.get("convert_error") or "unknown_error"
                error_labels[lbl] = error_labels.get(lbl, 0) + 1
            for lbl, cnt in error_labels.items():
                p(f"  {'':12} ERROR ({cnt}x): {lbl}")
    p("-" * 120)

    # ── B. Per-pair side-by-side ─────────────────────────────────────────────
    p("\n[B] PER-PAIR RESULTS (same SAS input, different Python outputs)")
    p("=" * 120)

    sas_inputs_uniq = {}
    for r in all_results:
        idx = r.get("task_index", 0)
        if idx not in sas_inputs_uniq:
            sas_inputs_uniq[idx] = r

    for idx in sorted(sas_inputs_uniq.keys()):
        base = sas_inputs_uniq[idx]
        p(f"\n  PAIR {idx+1}/6  |  Category: {base['category']}  |  Complexity: {base['complexity']}  |  Failure mode: {base.get('failure_mode') or 'none'}")
        p(f"  Description: {base.get('description','')[:100]}")
        p()
        p(f"  SAS CODE ({base['sas_code'].count(chr(10))+1} lines):")
        for line in base["sas_code"].split("\n")[:8]:
            p(f"    {line}")
        if base["sas_code"].count("\n") > 8:
            p(f"    ... ({base['sas_code'].count(chr(10))+1 - 8} more lines)")
        p()

        pair_rows = [r for r in all_results if r.get("task_index") == idx]
        p(f"  {'Provider':<12} {'Conf':>6} {'Eq?':>5} {'Lines':>6} {'Time':>8}  {'Issues / Error'}")
        p(f"  {'-'*12} {'-'*6} {'-'*5} {'-'*6} {'-'*8}  {'-'*55}")
        for r in sorted(pair_rows, key=lambda x: x.get("confidence", 0), reverse=True):
            if r.get("convert_ok"):
                issues_str = ", ".join(r.get("issues", [])) or "none"
                py_lines = r["python_code"].count("\n") + 1
                eq_str = "YES" if r.get("equivalent") else "NO "
                p(
                    f"  {r['provider']:<12} "
                    f"{r.get('confidence',0):>6.3f} "
                    f"{eq_str:>5} "
                    f"{py_lines:>6} "
                    f"{r.get('t_convert_s',0):>7.1f}s  "
                    f"{issues_str[:55]}"
                )
            else:
                err_label = r.get("convert_error") or "unknown_error"
                p(
                    f"  {r['provider']:<12} "
                    f"{'---':>6} "
                    f"{'ERR':>5} "
                    f"{'0':>6} "
                    f"{r.get('t_convert_s',0):>7.1f}s  "
                    f"FAILED: {err_label[:55]}"
                )

        # Show Python output per provider (first 6 lines)
        p()
        for r in sorted(pair_rows, key=lambda x: x.get("confidence", 0), reverse=True):
            if r.get("python_code"):
                p(f"  -- Python [{r['provider']}] (conf={r.get('confidence',0):.2f}) --")
                for line in r["python_code"].split("\n")[:6]:
                    p(f"    {line}")
                if r["python_code"].count("\n") > 6:
                    p(f"    ... ({r['python_code'].count(chr(10))+1 - 6} more lines)")
                p()

        p("  " + "=" * 80)

    # ── C. Head-to-head quality matrix ──────────────────────────────────────
    p("\n[C] HEAD-TO-HEAD QUALITY MATRIX (confidence per pair per provider)")
    p("-" * 120)
    pair_labels = [f"P{i+1}:{sas_inputs_uniq[i]['category'][:18]}" for i in sorted(sas_inputs_uniq.keys())]
    p(f"  {'Provider':<14} " + "  ".join(f"{lbl[:20]:>22}" for lbl in pair_labels) + f"  {'AVG':>6}")
    p(f"  {'-'*14} " + "  ".join("-" * 22 for _ in pair_labels) + f"  {'---':>6}")

    for prov in providers_used:
        row_confs = []
        cells = []
        for idx in sorted(sas_inputs_uniq.keys()):
            r_list = [r for r in all_results if r.get("provider") == prov and r.get("task_index") == idx]
            if r_list:
                r = r_list[0]
                if r.get("convert_ok"):
                    conf = r.get("confidence", 0)
                    eq = "Y" if r.get("equivalent") else "N"
                    cells.append(f"{conf:.3f}({eq})")
                    row_confs.append(conf)
                else:
                    # Classify failure into a short code for the matrix cell
                    err = r.get("convert_error") or "ERR"
                    if "429" in err:
                        code = "429:RateLimit"
                    elif "connection" in err.lower():
                        code = "ConnErr"
                    elif "400" in err:
                        code = "400:Schema"
                    elif "401" in err or "auth" in err.lower():
                        code = "401:Auth"
                    elif "404" in err:
                        code = "404:NotFound"
                    elif "504" in err:
                        code = "504:Timeout"
                    elif "5xx" in err or "500" in err:
                        code = "5xx:Server"
                    else:
                        code = "ERR"
                    cells.append(f"[{code}]")
            else:
                cells.append("  --  ")
        avg = sum(row_confs) / max(len(row_confs), 1) if row_confs else 0.0
        p(f"  {prov:<14} " + "  ".join(f"{c:>22}" for c in cells) + f"  {avg:>6.3f}")

    # ── D. Model profiles ────────────────────────────────────────────────────
    p("\n[D] MODEL PROFILES")
    p("=" * 120)
    MODEL_INFO = {
        "groq_gen":  {"params": "70B dense",     "arch": "LLaMA-3.3",   "ctx": "128K", "speed": "FAST (<2s)", "notes": "Groq hardware, excellent for SAS logic"},
        "mistral":   {"params": "~22B active MoE","arch": "Mistral MoE", "ctx": "128K", "speed": "SLOW (60-300s on free NIM)", "notes": "Strong instruction following, free tier rate limited"},
        "kimi":      {"params": "1T MoE (~32B act)","arch":"MoE Transformer","ctx":"128K","speed":"SLOW on NIM", "notes": "Large capacity, strong reasoning, less tested on SAS"},
        "gemini":    {"params": "Flash (small)",  "arch": "Gemini 2.0",  "ctx": "1M",   "speed": "FAST",       "notes": "Very large context, fast, good multilingual"},
        "azure":     {"params": "GPT-4o",         "arch": "OpenAI GPT",  "ctx": "128K", "speed": "FAST",       "notes": "Primary production model, highest quality expected"},
    }
    for prov in providers_used:
        info = MODEL_INFO.get(prov, {})
        rows = [r for r in all_results if r.get("provider") == prov]
        ok = [r for r in rows if r.get("convert_ok")]
        confs = [r.get("confidence", 0) for r in rows]
        avg_conf = sum(confs) / max(len(confs), 1)
        p(f"\n  [{prov.upper()}]  {rows[0].get('model','?') if rows else '?'}")
        p(f"    Params    : {info.get('params','?')}")
        p(f"    Arch      : {info.get('arch','?')}")
        p(f"    Context   : {info.get('ctx','?')}")
        p(f"    Speed     : {info.get('speed','?')}")
        p(f"    Notes     : {info.get('notes','?')}")
        p(f"    Results   : {len(ok)}/{len(rows)} converted  |  avg confidence={avg_conf:.3f}")
        top_issues: dict[str, int] = {}
        for r in rows:
            for iss in r.get("issues", []):
                if iss and iss not in ("none", "conversion_failed", "verify_failed"):
                    top_issues[iss] = top_issues.get(iss, 0) + 1
        if top_issues:
            p(f"    Top issues: " + ", ".join(f"{k}({v}x)" for k, v in sorted(top_issues.items(), key=lambda x: -x[1])[:4]))

    # ── E. Recommendation ───────────────────────────────────────────────────
    p("\n[E] RECOMMENDATION")
    p("=" * 120)
    prov_scores: dict[str, float] = {}
    for prov in providers_used:
        rows = [r for r in all_results if r.get("provider") == prov]
        ok = [r for r in rows if r.get("convert_ok")]
        if not rows:
            continue
        confs = [r.get("confidence", 0) for r in rows]
        avg_conf = sum(confs) / max(len(confs), 1)
        acc_rate = len(ok) / max(len(rows), 1)
        conv_times = [r["t_convert_s"] for r in ok]
        avg_t = sum(conv_times) / max(len(conv_times), 1)
        # Score: weighted quality + speed bonus
        speed_score = max(0, 1 - avg_t / 300)  # normalize to 300s max
        prov_scores[prov] = avg_conf * 0.6 + acc_rate * 0.3 + speed_score * 0.1

    if prov_scores:
        ranked = sorted(prov_scores.items(), key=lambda x: -x[1])
        p(f"  Ranking by score (60% confidence + 30% acceptance + 10% speed):")
        for rank, (prov, score) in enumerate(ranked, 1):
            p(f"  #{rank}  {prov:<12}  score={score:.3f}")
        winner = ranked[0][0]
        p(f"\n  WINNER: {winner.upper()} — {PROVIDERS[winner]['label']}")
        p(f"  Recommended for KB expansion: {winner} (best quality/speed balance)")


# ── Save results ─────────────────────────────────────────────────────────────

def save_results(
    run_id: str,
    sas_inputs: list[dict],
    all_results: list[dict],
    providers_used: list[str],
    kb_dir: str = "knowledge_base",
) -> None:
    os.makedirs(kb_dir, exist_ok=True)

    # Save fixed SAS inputs (reusable for future runs)
    sas_path = os.path.join(kb_dir, f"fixed_sas_{run_id}.json")
    with open(sas_path, "w", encoding="utf-8") as f:
        json.dump(sas_inputs, f, indent=2, default=str)
    print(f"\n  SAS inputs saved: {sas_path}")

    # Save full results
    results_path = os.path.join(kb_dir, f"benchmark_crossProvider_{run_id}.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump({
            "run_id":         run_id,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "methodology":    "fixed_sas_cross_provider",
            "providers":      providers_used,
            "sas_inputs":     sas_inputs,
            "results":        all_results,
        }, f, indent=2, default=str)
    print(f"  Full results saved: {results_path}")

    # Save verified pairs to the main generated_pairs files
    for prov in providers_used:
        prov_results = [r for r in all_results if r.get("provider") == prov and r.get("convert_ok") and r.get("confidence", 0) >= 0.65]
        if prov_results:
            pairs = []
            for r in prov_results:
                pairs.append({
                    "example_id":          str(uuid.uuid4()),
                    "sas_code":            r["sas_code"],
                    "python_code":         r["python_code"],
                    "partition_type":      r["category"],
                    "complexity_tier":     r["complexity"],
                    "target_runtime":      "python",
                    "verified":            True,
                    "source":              f"benchmark_{run_id}",
                    "failure_mode":        r.get("failure_mode", ""),
                    "verification_method": "llm_crosscheck",
                    "verification_score":  r["confidence"],
                    "category":            r["category"],
                    "provider":            prov,
                    "gen_model":           r["model"],
                    "verify_model":        r.get("verify_model", "llama-3.3-70b-versatile"),
                    "latency_s":           r.get("t_convert_s", 0),
                    "created_at":          datetime.now(timezone.utc).isoformat(),
                })
            prov_path = os.path.join(kb_dir, f"generated_pairs_{prov}_benchmark_{run_id}.json")
            with open(prov_path, "w", encoding="utf-8") as f:
                json.dump(pairs, f, indent=2, default=str)
            print(f"  {len(pairs)} verified pairs ({prov}) -> {prov_path}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    global _GROQ_KEYS

    parser = argparse.ArgumentParser(description="Cross-provider KB benchmark")
    parser.add_argument(
        "--providers", nargs="+",
        choices=list(PROVIDERS.keys()),
        default=["groq_gen"],
        help="Providers to benchmark for Python conversion.",
    )
    parser.add_argument(
        "--fixed-sas", default=None,
        help="Path to existing fixed_sas_*.json — skip SAS generation step.",
    )
    parser.add_argument(
        "--kb-dir", default="knowledge_base/output",
        help="Directory for output files (default: knowledge_base/output).",
    )
    args = parser.parse_args()

    # Load Groq keys
    for suffix in ("", "_2", "_3", "_4", "_5"):
        k = os.getenv(f"GROQ_API_KEY{suffix}", "")
        if k:
            _GROQ_KEYS.append(k)
    if not _GROQ_KEYS:
        print("ERROR: No GROQ_API_KEY found. Groq is required for SAS generation and verification.")
        sys.exit(1)
    print(f"Groq keys available: {len(_GROQ_KEYS)}")

    run_id = str(uuid.uuid4())[:8]
    print(f"Run ID: {run_id}")
    print(f"Providers: {args.providers}")

    # Step 1: SAS inputs
    if args.fixed_sas:
        print(f"\n[Step 1] Loading SAS inputs from {args.fixed_sas} ...")
        with open(args.fixed_sas, encoding="utf-8") as f:
            sas_inputs = json.load(f)
        print(f"  Loaded {len(sas_inputs)} SAS inputs.")
    else:
        sas_inputs = generate_sas_inputs(run_id)
        if not sas_inputs:
            print("ERROR: No SAS inputs generated. Aborting.")
            sys.exit(1)

    # Step 2: Convert with each provider
    all_results: list[dict] = []
    for provider_name in args.providers:
        results = convert_with_provider(sas_inputs, provider_name)
        all_results.extend(results)

    if not all_results:
        print("ERROR: No conversion results. Check API keys and provider availability.")
        sys.exit(1)

    # Step 3: Verify
    all_results = verify_results(all_results)

    # Step 4: Tableau
    print_tableau(all_results, run_id, args.providers)

    # Save
    save_results(run_id, sas_inputs, all_results, args.providers, args.kb_dir)

    print(f"\nDone. Run ID: {run_id}")


if __name__ == "__main__":
    main()
