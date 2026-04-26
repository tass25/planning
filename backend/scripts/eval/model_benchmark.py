"""model_benchmark.py  --  Run 3 Ollama models on torture_test.sas.

For each model the script:
  1. Translates every SAS block via the Ollama API
  2. Saves  output/benchmark/translation_<model>.py   (annotated with all metrics)
  3. Runs   Z3 on every translation
  4. Writes output/benchmark/benchmark.md             (comparison table)

Metrics captured per block x model:
  latency_s           wall-clock time for the API call
  prompt_tokens       from response.usage.prompt_tokens
  completion_tokens   from response.usage.completion_tokens
  tokens_per_second   completion_tokens / latency_s
  confidence          LLM self-reported score (0-1)
  python_loc          non-blank lines of generated Python
  syntax_valid        ast.parse() check (True/False)
  z3_status           formal_proof / counterexample / unverifiable
  z3_pattern          which Z3 pattern fired
  z3_latency_ms       Z3 solver time

Usage:
    cd backend
    python scripts/eval/model_benchmark.py

    # custom SAS file or model list:
    python scripts/eval/model_benchmark.py --sas path/to/file.sas
    python scripts/eval/model_benchmark.py --models minimax-m2.7:cloud,deepseek-v3.2

Requires:  OLLAMA_API_KEY  and  OLLAMA_BASE_URL  in .env
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# --- path setup -----------------------------------------------------------
_HERE = Path(__file__).resolve().parent
BACKEND_DIR = _HERE
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR.parent / ".env")


# ==========================================================================
# CONFIG
# ==========================================================================

MODELS = [
    "minimax-m2.7:cloud",
    "qwen3-coder-next",
    "deepseek-v3.2",
    "nemotron-3-super:cloud",
]

SYSTEM_PROMPT = """\
You are an expert SAS-to-Python translator. Translate the SAS code to idiomatic
Python (pandas / NumPy / statsmodels). Rules:
1. Output ONLY a JSON object  -- no markdown, no prose.
2. Preserve exact semantics:
   - PROC MEANS CLASS  ->  groupby([...], dropna=False).agg(...)
   - LEFT JOIN         ->  pd.merge(..., how='left')
   - PROC SORT DESCENDING col  ->  sort_values(..., ascending=[..., False])
   - PROC SORT NODUPKEY  ->  sort_values(...).drop_duplicates(subset=[...])
   - IF/THEN/ELSE      ->  np.select / np.where  (never iterrows)
3. Add brief inline comments for complex SAS idioms.
4. Start the python_code with all required imports.

Output format:
{
  "python_code": "<valid Python>",
  "imports_detected": ["import pandas as pd", ...],
  "confidence": 0.0-1.0,
  "notes": "<one line translator notes>"
}
"""


# ==========================================================================
# SAS block parser
# ==========================================================================

_SAS_STMT = re.compile(
    r"^\s*(data\s+\w|proc\s+\w|%macro\b|%let\b|run\s*;|quit\s*;)",
    re.IGNORECASE | re.MULTILINE,
)


def _has_sas(text: str) -> bool:
    return bool(_SAS_STMT.search(text))


def parse_blocks(sas_path: Path) -> list[tuple[str, str]]:
    """Return [(label, sas_code), ...] from a SAS file."""
    text = sas_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks: list[tuple[str, str]] = []
    cur_label = "block_0"
    cur_lines: list[str] = []

    for line in lines:
        m = re.match(r"/\*\s*[─\-]+\s*(\d+\.\s*.+?)\s*[─\-]+\s*\*/", line)
        if not m:
            m = re.match(r"/\*\s*(\d+\.\s*.+?)\s*\*/", line.strip())
        if m:
            code = "\n".join(cur_lines).strip()
            if code and _has_sas(code):
                blocks.append((cur_label, code))
            cur_label = m.group(1).strip()
            cur_lines = []
        else:
            cur_lines.append(line)

    code = "\n".join(cur_lines).strip()
    if code and _has_sas(code):
        blocks.append((cur_label, code))
    return blocks


def _risk(src: str) -> str:
    s = src.lower()
    if "%macro" in s or "proc sql" in s:
        return "MOD"
    if "hash" in s or "first." in s or "retain" in s:
        return "HIGH"
    return "LOW"


# ==========================================================================
# LLM call  -- raw OpenAI-compatible, captures usage
# ==========================================================================


def call_ollama(model: str, sas_code: str, api_key: str, base_url: str) -> dict:
    """Call Ollama and return raw dict with python_code, tokens, latency."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=300.0)
    t0 = time.monotonic()
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Translate this SAS code:\n\n```sas\n{sas_code}\n```"},
            ],
            temperature=0.1,
            max_tokens=2048,
        )
    except Exception as exc:
        return {"error": str(exc), "latency_s": time.monotonic() - t0}

    latency = time.monotonic() - t0
    raw = resp.choices[0].message.content or ""
    usage = resp.usage
    return {
        "raw": raw,
        "latency_s": latency,
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }


# ==========================================================================
# Response parser
# ==========================================================================

_JSON_RE = re.compile(r"\{[\s\S]+\}", re.DOTALL)
_PY_FENCE = re.compile(r"```(?:python)?\s*([\s\S]+?)\s*```", re.IGNORECASE)


def parse_response(raw: str) -> tuple[str, list[str], float, str]:
    """Return (python_code, imports, confidence, notes)."""
    # Try to extract a JSON object
    jm = _JSON_RE.search(raw)
    if jm:
        try:
            obj = json.loads(jm.group(0))
            code = obj.get("python_code", "").strip()
            if code:
                return (
                    code,
                    obj.get("imports_detected", []),
                    float(obj.get("confidence", 0.7)),
                    obj.get("notes", ""),
                )
        except (json.JSONDecodeError, ValueError):
            pass

    # Try a python code fence
    pm = _PY_FENCE.search(raw)
    if pm:
        code = pm.group(1).strip()
        imps = [l for l in code.splitlines() if l.strip().startswith(("import ", "from "))]
        return code, imps, 0.6, "extracted from code fence"

    # Fallback: strip markdown artefacts from raw text
    code = re.sub(r"^```\w*\n?", "", raw.strip())
    code = re.sub(r"\n?```$", "", code).strip()
    imps = [l for l in code.splitlines() if l.strip().startswith(("import ", "from "))]
    return code, imps, 0.5, "raw fallback"


# ==========================================================================
# Syntax check
# ==========================================================================


def check_syntax(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, str(e)


# ==========================================================================
# Z3 check
# ==========================================================================


def run_z3(sas_code: str, python_code: str) -> tuple[str, str, str, float]:
    """Return (status_value, pattern, issue, latency_ms)."""
    try:
        from partition.verification.z3_agent import Z3VerificationAgent

        agent = Z3VerificationAgent()
        t0 = time.monotonic()
        res = agent.verify(sas_code, python_code)
        lat = (time.monotonic() - t0) * 1000
        issue = res.counterexample.get("issue", "") if res.counterexample else ""
        return res.status.value, res.pattern, issue, lat
    except Exception as exc:
        return "error", "", str(exc), 0.0


# ==========================================================================
# Data model
# ==========================================================================


@dataclass
class BlockResult:
    model: str
    block_index: int
    block_label: str
    risk: str
    sas_lines: int
    # timing & tokens
    latency_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tokens_per_second: float = 0.0
    # quality
    status: str = "PARTIAL"
    confidence: float = 0.0
    python_loc: int = 0
    import_count: int = 0
    syntax_valid: bool = False
    syntax_error: str = ""
    # Z3
    z3_status: str = "skipped"
    z3_pattern: str = ""
    z3_issue: str = ""
    z3_latency_ms: float = 0.0
    # raw
    python_code: str = ""
    error_msg: str = ""


# ==========================================================================
# Single block translation
# ==========================================================================


def translate_block(
    model: str, idx: int, label: str, sas: str, api_key: str, base_url: str
) -> BlockResult:
    risk = _risk(sas)
    sas_lines = len([l for l in sas.splitlines() if l.strip()])

    data = call_ollama(model, sas, api_key, base_url)

    if "error" in data:
        return BlockResult(
            model=model,
            block_index=idx,
            block_label=label,
            risk=risk,
            sas_lines=sas_lines,
            latency_s=data.get("latency_s", 0.0),
            status="PARTIAL",
            error_msg=data["error"],
        )

    python_code, imports, confidence, _ = parse_response(data["raw"])
    lat = data["latency_s"]
    ptok = data["prompt_tokens"]
    ctok = data["completion_tokens"]
    ttok = data["total_tokens"]
    tps = ctok / lat if lat > 0 and ctok > 0 else 0.0

    if not python_code:
        return BlockResult(
            model=model,
            block_index=idx,
            block_label=label,
            risk=risk,
            sas_lines=sas_lines,
            latency_s=lat,
            prompt_tokens=ptok,
            completion_tokens=ctok,
            total_tokens=ttok,
            tokens_per_second=tps,
            confidence=confidence,
            status="PARTIAL",
            error_msg="empty python_code after parse",
        )

    syntax_ok, syntax_err = check_syntax(python_code)
    loc = len([l for l in python_code.splitlines() if l.strip()])
    status = "SUCCESS" if syntax_ok and confidence >= 0.5 else "PARTIAL"

    z3_st, z3_pat, z3_issue, z3_lat = run_z3(sas, python_code)

    return BlockResult(
        model=model,
        block_index=idx,
        block_label=label,
        risk=risk,
        sas_lines=sas_lines,
        latency_s=lat,
        prompt_tokens=ptok,
        completion_tokens=ctok,
        total_tokens=ttok,
        tokens_per_second=tps,
        status=status,
        confidence=confidence,
        python_loc=loc,
        import_count=len(imports),
        syntax_valid=syntax_ok,
        syntax_error=syntax_err,
        z3_status=z3_st,
        z3_pattern=z3_pat,
        z3_issue=z3_issue,
        z3_latency_ms=z3_lat,
        python_code=python_code,
    )


# ==========================================================================
# Per-model translation file
# ==========================================================================


def _safe(model: str) -> str:
    return re.sub(r"[^\w.-]", "_", model)


def save_translation(
    model: str, results: list[BlockResult], blocks: list[tuple[str, str]], out_dir: Path
) -> Path:
    path = out_dir / f"translation_{_safe(model)}.py"
    run_ts = datetime.now(timezone.utc).isoformat()

    success = sum(1 for r in results if r.status == "SUCCESS")
    proved = sum(1 for r in results if r.z3_status == "formal_proof")
    total = len(results)
    mean_lat = sum(r.latency_s for r in results) / total if total else 0
    total_tok = sum(r.total_tokens for r in results)

    lines = [
        '"""',
        f"translation_{_safe(model)}.py",
        "",
        f"Model        : {model}",
        f"Generated    : {run_ts}",
        f"Blocks       : {total}",
        f"Success      : {success}/{total}  ({success * 100 // total if total else 0}%)",
        f"Z3 proved    : {proved}/{total}",
        f"Mean latency : {mean_lat:.1f}s",
        f"Total tokens : {total_tok:,}",
        '"""',
        "",
    ]

    SEP = "# " + "=" * 76

    for i, (label, sas) in enumerate(blocks):
        r = next((x for x in results if x.block_index == i), None)
        lines += [
            SEP,
            f"# Block {i + 1:02d}  {label}",
            f"# Risk       : {_risk(sas)}",
            f"# SAS lines  : {len([l for l in sas.splitlines() if l.strip()])}",
        ]
        if r:
            lines += [
                f"# Status     : {r.status}",
                f"# Syntax OK  : {r.syntax_valid}{'  error: ' + r.syntax_error if r.syntax_error else ''}",
                f"# Confidence : {r.confidence:.2f}",
                f"# Latency    : {r.latency_s:.1f}s",
                f"# Tokens     : {r.total_tokens}  "
                f"({r.prompt_tokens} prompt + {r.completion_tokens} completion)",
                f"# tok/s      : {r.tokens_per_second:.0f}",
                f"# Z3 status  : {r.z3_status}",
                f"# Z3 pattern : {r.z3_pattern or '-'}",
                f"# Z3 lat ms  : {r.z3_latency_ms:.1f}",
            ]
            if r.z3_issue:
                lines.append(f"# Z3 issue   : {r.z3_issue[:100]}")
            lines.append("#")
            lines += [f"# SAS: {l}" for l in sas.splitlines()]
            lines += [SEP, ""]
            lines.append(r.python_code if r.python_code else f"# PARTIAL: {r.error_msg}")
        else:
            lines += [SEP, "# ERROR: no result"]
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ==========================================================================
# benchmark.md
# ==========================================================================

_Z3_ICON = {
    "formal_proof": "PROVED",
    "counterexample": "!! COUNTEREX",
    "unverifiable": "unknown",
    "error": "error",
    "skipped": "skipped",
}


def write_benchmark_md(
    models: list[str],
    all_results: dict[str, list[BlockResult]],
    blocks: list[tuple[str, str]],
    out_path: Path,
    run_ts: str,
) -> None:
    def _short(m: str) -> str:
        return (
            m.split(":")[0]
            .replace("minimax-m2.7", "minimax")
            .replace("qwen3-coder-next", "qwen3")
            .replace("nemotron-3-super", "nemotron")
        )

    def _pct(n, t):
        return f"{n * 100 // t if t else 0}%"

    lines: list[str] = [
        "# Codara  --  Model Benchmark",
        "",
        f"**Run:** {run_ts}",
        f"**SAS file:** torture_test.sas  ({len(blocks)} blocks)",
        f"**Models:** {', '.join(models)}",
        "",
        "---",
        "",
        "## 1. Aggregate",
        "",
    ]

    # Build summary per model
    summaries = {}
    for model in models:
        rs = all_results.get(model, [])
        n = len(rs)
        summaries[model] = {
            "n": n,
            "success": sum(1 for r in rs if r.status == "SUCCESS"),
            "syntax": sum(1 for r in rs if r.syntax_valid),
            "total_lat": sum(r.latency_s for r in rs),
            "mean_lat": sum(r.latency_s for r in rs) / n if n else 0,
            "p95_lat": sorted(r.latency_s for r in rs)[int(n * 0.95)] if rs else 0,
            "prompt_tok": sum(r.prompt_tokens for r in rs),
            "compl_tok": sum(r.completion_tokens for r in rs),
            "total_tok": sum(r.total_tokens for r in rs),
            "mean_tps": sum(r.tokens_per_second for r in rs if r.tokens_per_second > 0)
            / max(1, sum(1 for r in rs if r.tokens_per_second > 0)),
            "mean_conf": sum(r.confidence for r in rs) / n if n else 0,
            "z3_proved": sum(1 for r in rs if r.z3_status == "formal_proof"),
            "z3_counterex": sum(1 for r in rs if r.z3_status == "counterexample"),
            "z3_unknown": sum(1 for r in rs if r.z3_status == "unverifiable"),
        }

    # Aggregate table
    sh = [_short(m) for m in models]
    lines += [
        f"| Metric | {' | '.join(sh)} |",
        f"|--------|{'|'.join(['----'] * len(models))}|",
    ]

    def _row(label, fn):
        vals = " | ".join(fn(summaries[m]) for m in models)
        return f"| {label} | {vals} |"

    lines += [
        _row("Success rate", lambda s: _pct(s["success"], s["n"])),
        _row("Syntax valid", lambda s: _pct(s["syntax"], s["n"])),
        _row("Mean confidence", lambda s: f"{s['mean_conf']:.2f}"),
        _row("Mean latency (s)", lambda s: f"{s['mean_lat']:.1f}"),
        _row("p95 latency (s)", lambda s: f"{s['p95_lat']:.1f}"),
        _row("Total time (s)", lambda s: f"{s['total_lat']:.0f}"),
        _row("Prompt tokens (total)", lambda s: f"{s['prompt_tok']:,}"),
        _row("Completion tokens", lambda s: f"{s['compl_tok']:,}"),
        _row("Total tokens", lambda s: f"{s['total_tok']:,}"),
        _row("Mean tok/s", lambda s: f"{s['mean_tps']:.0f}"),
        _row("Z3 formally proved", lambda s: f"{s['z3_proved']}/{s['n']}"),
        _row("Z3 counterexamples", lambda s: f"{s['z3_counterex']}/{s['n']}"),
        _row("Z3 unknown", lambda s: f"{s['z3_unknown']}/{s['n']}"),
        "",
        "---",
        "",
        "## 2. Block-by-Block",
        "",
    ]

    for i, (label, sas) in enumerate(blocks):
        lines += [
            f"### Block {i + 1}: {label}",
            f"Risk: {_risk(sas)} | SAS lines: {len([l for l in sas.splitlines() if l.strip()])}",
            "",
            f"| Metric | {' | '.join(sh)} |",
            f"|--------|{'|'.join(['----'] * len(models))}|",
        ]

        def _brow(lbl, fn):
            vals = []
            for m in models:
                r = next((x for x in all_results.get(m, []) if x.block_index == i), None)
                vals.append(fn(r) if r else "N/A")
            return f"| {lbl} | {' | '.join(vals)} |"

        lines += [
            _brow("Status", lambda r: r.status),
            _brow("Latency (s)", lambda r: f"{r.latency_s:.1f}"),
            _brow("Prompt tokens", lambda r: str(r.prompt_tokens)),
            _brow("Compl. tokens", lambda r: str(r.completion_tokens)),
            _brow("tok/s", lambda r: f"{r.tokens_per_second:.0f}"),
            _brow("Confidence", lambda r: f"{r.confidence:.2f}"),
            _brow("Python LOC", lambda r: str(r.python_loc)),
            _brow(
                "Syntax valid", lambda r: "yes" if r.syntax_valid else f"NO: {r.syntax_error[:40]}"
            ),
            _brow("Z3 result", lambda r: _Z3_ICON.get(r.z3_status, r.z3_status)),
            _brow("Z3 pattern", lambda r: r.z3_pattern or "-"),
            _brow("Z3 lat (ms)", lambda r: f"{r.z3_latency_ms:.1f}"),
        ]
        lines.append("")

    lines += [
        "---",
        "",
        "## 3. Translation snippets (first 12 lines)",
        "",
    ]
    for i, (label, _) in enumerate(blocks):
        lines += [f"### Block {i + 1}: {label}", ""]
        for model in models:
            r = next((x for x in all_results.get(model, []) if x.block_index == i), None)
            lines += [f"**{_short(model)}**", "```python"]
            if r and r.python_code:
                snippet = "\n".join(r.python_code.splitlines()[:12])
                lines.append(snippet)
                extra = r.python_loc - 12
                if extra > 0:
                    lines.append(f"# ... {extra} more lines")
            else:
                lines.append(f"# PARTIAL: {r.error_msg if r else 'no result'}")
            lines += ["```", ""]

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ==========================================================================
# Main
# ==========================================================================


def run(sas_path: Path, models: list[str]) -> None:
    api_key = os.getenv("OLLAMA_API_KEY", "")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not api_key:
        print("ERROR: OLLAMA_API_KEY not set in .env")
        sys.exit(1)

    blocks = parse_blocks(sas_path)
    if not blocks:
        print(f"ERROR: no SAS blocks found in {sas_path}")
        sys.exit(1)

    out_dir = BACKEND_DIR / "output" / "benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\nCodara Model Benchmark")
    print(f"  SAS    : {sas_path.name}  ({len(blocks)} blocks)")
    print(f"  Models : {', '.join(models)}")
    print(f"  Output : {out_dir}\n")

    all_results: dict[str, list[BlockResult]] = {}

    for model in models:
        print(f"\n--- Model: {model} ---")
        results: list[BlockResult] = []
        model_t0 = time.monotonic()

        for i, (label, sas) in enumerate(blocks):
            short_lbl = f"[{i + 1:2d}/{len(blocks)}] {label[:45]:<45}"
            print(f"  {short_lbl}", end="", flush=True)

            r = translate_block(model, i, label, sas, api_key, base_url)
            results.append(r)

            s_icon = "OK" if r.status == "SUCCESS" else "--"
            x_icon = "ok" if r.syntax_valid else "!!"
            z_icon = {
                "formal_proof": "proved",
                "counterexample": "!! COUNTEREX",
                "unverifiable": "unknown",
                "skipped": "skip",
            }.get(r.z3_status, "?")
            tok = f"{r.total_tokens}tok" if r.total_tokens else "?tok"
            print(
                f" {s_icon}  {r.latency_s:5.1f}s  {tok:>7}"
                f"  {r.tokens_per_second:>4.0f}t/s"
                f"  conf={r.confidence:.2f}"
                f"  syn={x_icon}"
                f"  z3={z_icon}"
            )
            if r.error_msg:
                print(f"    ! {r.error_msg[:80]}")

        model_elapsed = time.monotonic() - model_t0
        all_results[model] = results

        success = sum(1 for r in results if r.status == "SUCCESS")
        proved = sum(1 for r in results if r.z3_status == "formal_proof")
        ttok = sum(r.total_tokens for r in results)
        print(
            f"\n  => {model}: {success}/{len(results)} success  "
            f"{proved}/{len(results)} z3-proved  "
            f"{ttok} tokens  {model_elapsed:.0f}s total"
        )

        py_path = save_translation(model, results, blocks, out_dir)
        print(f"     saved: {py_path.name}")

    # benchmark.md
    md_path = out_dir / "benchmark.md"
    write_benchmark_md(models, all_results, blocks, md_path, run_ts)

    # benchmark.json
    json_path = out_dir / "benchmark.json"
    json_path.write_text(
        json.dumps(
            {
                "run_timestamp": run_ts,
                "sas_file": str(sas_path),
                "models": models,
                "results": {model: [asdict(r) for r in rs] for model, rs in all_results.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n  benchmark.md   -> {md_path}")
    print(f"  benchmark.json -> {json_path}\n")

    # Final comparison
    print("FINAL COMPARISON")
    print(f"  {'Metric':<28}" + "".join(f"{m.split(':')[0][:16]:>18}" for m in models))
    print("  " + "-" * (28 + 18 * len(models)))

    def _cmp(label, fn):
        row = f"  {label:<28}"
        for m in models:
            rs = all_results.get(m, [])
            row += f"{fn(rs):>18}"
        print(row)

    total = len(blocks)
    _cmp(
        "Success rate",
        lambda rs: f"{sum(1 for r in rs if r.status == 'SUCCESS') * 100 // total if total else 0}%",
    )
    _cmp(
        "Syntax valid",
        lambda rs: f"{sum(1 for r in rs if r.syntax_valid) * 100 // total if total else 0}%",
    )
    _cmp(
        "Mean confidence",
        lambda rs: f"{sum(r.confidence for r in rs) / len(rs):.2f}" if rs else "N/A",
    )
    _cmp(
        "Mean latency (s)",
        lambda rs: f"{sum(r.latency_s for r in rs) / len(rs):.1f}" if rs else "N/A",
    )
    _cmp("Total tokens", lambda rs: f"{sum(r.total_tokens for r in rs):,}")
    _cmp(
        "Mean tok/s",
        lambda rs: (
            f"{sum(r.tokens_per_second for r in rs if r.tokens_per_second > 0) / max(1, sum(1 for r in rs if r.tokens_per_second > 0)):.0f}"
        ),
    )
    _cmp("Z3 proved", lambda rs: f"{sum(1 for r in rs if r.z3_status == 'formal_proof')}/{total}")
    _cmp(
        "Z3 counterexamples",
        lambda rs: f"{sum(1 for r in rs if r.z3_status == 'counterexample')}/{total}",
    )
    print()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--sas", type=Path, default=BACKEND_DIR / "tests" / "fixtures" / "torture_test.sas"
    )
    p.add_argument("--models", type=str, default=",".join(MODELS))
    args = p.parse_args()

    sas_path = args.sas.resolve()
    if not sas_path.exists():
        print(f"ERROR: {sas_path} not found")
        sys.exit(1)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    run(sas_path, models)


if __name__ == "__main__":
    main()
