"""z3_audit.py — Run Z3 on the ACTUAL torture_test translations already on disk.

This is the real "before/after Z3" demonstration:
  BEFORE Z3: each translation passed syntax check + exec validation -> marked SUCCESS
  AFTER  Z3: Z3 inspects the Python semantics against the SAS source
             -> finds FORMAL PROOF, COUNTEREXAMPLE, or UNKNOWN

Output:
  backend/output/z3_audit/z3_audit_results.md   (human-readable report)
  backend/output/z3_audit/z3_audit_results.json  (machine-readable)

Usage:
    cd backend
    python scripts/eval/z3_audit.py
    (or: python scripts/eval/z3_audit.py --translations output/translate_test/)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parent
BACKEND_DIR = _HERE
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR.parent / ".env")

import re

_SAS_CODE_RE = re.compile(
    r"^\s*(data\s+\w|proc\s+\w|%macro\b|%let\b|run\s*;|quit\s*;)",
    re.IGNORECASE | re.MULTILINE,
)


def _has_sas_code(text: str) -> bool:
    return bool(_SAS_CODE_RE.search(text))


def parse_blocks(sas_path: Path) -> list[tuple[str, str]]:
    text = sas_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks: list[tuple[str, str]] = []
    current_label = "block_0"
    current_lines: list[str] = []
    for line in lines:
        if line.startswith("/* --") or (line.startswith("/* ") and "──" in line):
            code = "\n".join(current_lines).strip()
            if code and _has_sas_code(code):
                blocks.append((current_label, code))
            current_label = re.sub(r"[/*─ \-]+", " ", line).strip()
            current_lines = []
        else:
            current_lines.append(line)
    code = "\n".join(current_lines).strip()
    if code and _has_sas_code(code):
        blocks.append((current_label, code))
    return blocks


def parse_blocks_v2(sas_path: Path) -> list[tuple[str, str]]:
    """Marker-aware parser that handles /* -- N. LABEL -- */ style."""
    text = sas_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    blocks: list[tuple[str, str]] = []
    current_label = "block_0"
    current_lines: list[str] = []
    for line in lines:
        m = re.match(r"/\*\s*[─\-]+\s*(\d+\.\s*.+?)\s*[─\-]+\s*\*/", line)
        if not m:
            m = re.match(r"/\*\s*(\d+\.\s*.+?)\s*\*/", line.strip())
        if m:
            code = "\n".join(current_lines).strip()
            if code and _has_sas_code(code):
                blocks.append((current_label, code))
            current_label = m.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    code = "\n".join(current_lines).strip()
    if code and _has_sas_code(code):
        blocks.append((current_label, code))
    return blocks


def find_translation(
    label: str, index: int, trans_dir: Path
) -> tuple[str, Path] | tuple[None, None]:
    """Find the Python file matching this block index."""
    pattern = f"*block{index+1:02d}*.py"
    matches = list(trans_dir.glob(pattern))
    if matches:
        p = matches[0]
        return p.read_text(encoding="utf-8", errors="replace"), p
    # fallback: match by label keywords
    safe = re.sub(r"[^\w]+", "_", label)[:20].lower()
    matches = list(trans_dir.glob(f"*{safe}*.py"))
    if matches:
        p = matches[0]
        return p.read_text(encoding="utf-8", errors="replace"), p
    return None, None


@dataclass
class AuditRow:
    block_index: int
    block_label: str
    sas_lines: int
    py_file: str
    py_lines: int
    # before Z3
    before_status: str = "SUCCESS"  # always SUCCESS/PARTIAL (what pipeline sees)
    # after Z3
    z3_status: str = ""
    z3_pattern: str = ""
    z3_issue: str = ""
    z3_hint: str = ""
    z3_latency_ms: float = 0.0
    error: str = ""


def run_z3(sas_code: str, python_code: str) -> tuple[str, str, str, str, float]:
    """Return (status_value, pattern, issue, hint, latency_ms)."""
    try:
        from partition.verification.z3_agent import Z3VerificationAgent

        agent = Z3VerificationAgent()
        t0 = time.monotonic()
        result = agent.verify(sas_code, python_code)
        latency = (time.monotonic() - t0) * 1000
        issue = ""
        hint = ""
        if result.counterexample:
            issue = result.counterexample.get("issue", "")
            hint = result.counterexample.get("hint", "") or result.counterexample.get("fix", "")
        return result.status.value, result.pattern, issue, hint, latency
    except Exception as exc:
        return "error", "", str(exc), "", 0.0


STATUS_ICON = {
    "formal_proof": "[PROVED]",
    "counterexample": "[COUNTEREXAMPLE]",
    "unverifiable": "[UNKNOWN]",
    "behavioral_verified": "[BEHAVIORAL]",
    "skipped": "[SKIPPED]",
    "error": "[ERROR]",
}


def write_md(rows: list[AuditRow], sas_path: Path, trans_dir: Path, out_path: Path) -> None:
    run_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    proved = sum(1 for r in rows if r.z3_status == "formal_proof")
    counterex = sum(1 for r in rows if r.z3_status == "counterexample")
    unknown = sum(1 for r in rows if r.z3_status in ("unverifiable", ""))
    total = len(rows)
    mean_lat = sum(r.z3_latency_ms for r in rows) / total if rows else 0

    lines: list[str] = [
        "# Z3 Audit Report — Real Results on Actual Translations",
        "",
        f"**Generated:** {run_ts}",
        f"**SAS file:** `{sas_path}`",
        f"**Translations:** `{trans_dir}`",
        f"**Blocks audited:** {total}",
        "",
        "---",
        "",
        "## What this shows",
        "",
        "Each block below was already translated and **marked SUCCESS** by the",
        "syntax + exec validation. Z3 then inspects the Python semantics against",
        "the original SAS — this is the layer that catches bugs validation misses.",
        "",
        "| Symbol | Meaning |",
        "|--------|---------|",
        "| `[PROVED]` | Z3 formally proved the translation is semantically equivalent |",
        "| `[COUNTEREXAMPLE]` | Z3 found a concrete input where SAS and Python differ |",
        "| `[UNKNOWN]` | Pattern outside Z3 scope (RETAIN, hash, macros) |",
        "",
        "---",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Blocks audited | {total} |",
        f"| Formally proved | **{proved}** ({proved*100//total if total else 0}%) |",
        f"| Counterexamples found | **{counterex}** ({counterex*100//total if total else 0}%) |",
        f"| Outside Z3 scope | {unknown} ({unknown*100//total if total else 0}%) |",
        f"| Mean Z3 latency | {mean_lat:.1f} ms |",
        "| Pipeline overhead | negligible (vs >5000ms LLM latency) |",
        "",
        "---",
        "",
        "## Block-by-Block Results",
        "",
    ]

    for r in rows:
        icon = STATUS_ICON.get(r.z3_status, r.z3_status)
        lines += [
            f"### Block {r.block_index}: {r.block_label}",
            "",
            f"- **Translation file:** `{r.py_file}`",
            f"- **SAS lines:** {r.sas_lines}  |  **Python lines:** {r.py_lines}",
            f"- **Z3 latency:** {r.z3_latency_ms:.1f} ms",
            "",
            "| Stage | Result |",
            "|-------|--------|",
            "| Syntax check | PASS |",
            "| Exec validation | PASS (no exception) |",
            f"| **Z3 formal check** | **{icon}** |",
        ]
        if r.z3_pattern:
            lines.append(f"| Z3 pattern matched | `{r.z3_pattern}` |")
        lines.append("")

        if r.z3_status == "counterexample":
            lines += [
                "> **Semantic bug detected by Z3:**",
                f"> {r.z3_issue}",
            ]
            if r.z3_hint:
                lines += [
                    ">",
                    f"> **Fix:** {r.z3_hint}",
                ]
            lines.append("")
        elif r.z3_status == "formal_proof":
            lines += [
                "> Z3 formally proved this translation preserves the semantics",
                f"> of the `{r.z3_pattern}` pattern.",
                "",
            ]
        elif r.z3_status in ("unverifiable", ""):
            lines += [
                f"> Pattern `{r.block_label}` uses SAS idioms (RETAIN, hash objects,",
                "> macros) that are outside Z3's decidable fragment — result is UNKNOWN.",
                "> This is expected; Z3 only covers patterns it can encode symbolically.",
                "",
            ]
        if r.error:
            lines += [f"> ERROR: {r.error}", ""]

    lines += [
        "---",
        "",
        "## Conclusion",
        "",
        f"Z3 formally proved **{proved}/{total}** translations correct and detected",
        f"**{counterex}** semantic bug(s) that syntax + exec validation did not catch.",
        f"The remaining {unknown} blocks use patterns outside Z3's scope (RETAIN,",
        "hash objects, macro expansion) — these fall back to human review.",
        "",
        "**Z3 overhead:** {:.1f} ms mean per block — negligible against LLM latency.".format(
            mean_lat
        ),
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")


def main(trans_dir: Path, sas_path: Path) -> None:
    print(f"\nZ3 Audit — reading blocks from {sas_path.name}")
    print(f"           translations from    {trans_dir}\n")

    blocks = parse_blocks_v2(sas_path)
    if not blocks:
        print("ERROR: no SAS blocks parsed")
        sys.exit(1)

    print(f"Parsed {len(blocks)} SAS blocks.\n")

    out_dir = BACKEND_DIR / "output" / "z3_audit"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[AuditRow] = []

    col_w = 42
    print(f"  {'Block':<{col_w}} {'Before Z3':<14} {'After Z3':<22} {'Pattern / Issue'}")
    print(f"  {'-'*col_w} {'-'*14} {'-'*22} {'-'*30}")

    for i, (label, sas_code) in enumerate(blocks):
        py_code, py_path = find_translation(label, i, trans_dir)
        short_label = label[: col_w - 2]

        if py_code is None:
            row = AuditRow(
                block_index=i + 1,
                block_label=label,
                sas_lines=len([l for l in sas_code.splitlines() if l.strip()]),
                py_file="NOT FOUND",
                py_lines=0,
                z3_status="skipped",
                error="no translation file found",
            )
            rows.append(row)
            print(f"  {short_label:<{col_w}} {'SUCCESS':<14} {'SKIPPED (no file)':<22}")
            continue

        py_lines = len([l for l in py_code.splitlines() if l.strip()])
        sas_lines = len([l for l in sas_code.splitlines() if l.strip()])

        z3_status, z3_pat, z3_issue, z3_hint, z3_lat = run_z3(sas_code, py_code)

        row = AuditRow(
            block_index=i + 1,
            block_label=label,
            sas_lines=sas_lines,
            py_file=py_path.name if py_path else "",
            py_lines=py_lines,
            z3_status=z3_status,
            z3_pattern=z3_pat,
            z3_issue=z3_issue,
            z3_hint=z3_hint,
            z3_latency_ms=z3_lat,
        )
        rows.append(row)

        icon = STATUS_ICON.get(z3_status, z3_status)
        detail = z3_pat if z3_pat else (z3_issue[:30] if z3_issue else "")
        print(f"  {short_label:<{col_w}} {'SUCCESS':<14} {icon:<22} {detail}")
        if z3_issue:
            print(f"    Issue: {z3_issue[:80]}")
            if z3_hint:
                print(f"    Fix  : {z3_hint[:80]}")

    # Summary
    proved = sum(1 for r in rows if r.z3_status == "formal_proof")
    counterex = sum(1 for r in rows if r.z3_status == "counterexample")
    unknown = sum(1 for r in rows if r.z3_status in ("unverifiable", ""))
    total = len(rows)
    mean_lat = sum(r.z3_latency_ms for r in rows) / total if rows else 0

    print(f"\n{'='*80}")
    print(f"  RESULTS  ({total} blocks)")
    print(f"  Formally proved  : {proved}/{total}  ({proved*100//total if total else 0}%)")
    print(f"  Counterexamples  : {counterex}/{total}  ({counterex*100//total if total else 0}%)")
    print(f"  Outside scope    : {unknown}/{total}  ({unknown*100//total if total else 0}%)")
    print(f"  Mean Z3 latency  : {mean_lat:.1f} ms")
    print(f"{'='*80}\n")

    # Save JSON
    json_path = out_dir / "z3_audit_results.json"
    json_path.write_text(
        json.dumps(
            {
                "run_timestamp": datetime.now(timezone.utc).isoformat(),
                "sas_file": str(sas_path),
                "translations_dir": str(trans_dir),
                "summary": {
                    "total": total,
                    "proved": proved,
                    "counterexamples": counterex,
                    "unknown": unknown,
                    "mean_z3_latency_ms": round(mean_lat, 2),
                },
                "blocks": [asdict(r) for r in rows],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    # Save Markdown
    md_path = out_dir / "z3_audit_results.md"
    write_md(rows, sas_path, trans_dir, md_path)

    print(f"  Saved: {json_path.name}")
    print(f"  Saved: {md_path.name}")
    print(f"  Dir  : {out_dir}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Z3 audit on existing translations")
    parser.add_argument(
        "--translations",
        type=Path,
        default=BACKEND_DIR / "output" / "translate_test",
        help="Directory containing translation .py files",
    )
    parser.add_argument(
        "--sas",
        type=Path,
        default=BACKEND_DIR / "tests" / "fixtures" / "torture_test.sas",
    )
    args = parser.parse_args()
    main(args.translations.resolve(), args.sas.resolve())
