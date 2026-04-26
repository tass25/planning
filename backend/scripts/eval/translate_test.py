"""translate_test.py — end-to-end translation test on torture_test.sas.

Runs the full TranslationPipeline (translate → validate → Z3) on
each block extracted from torture_test.sas and prints a summary table.

Usage:
    cd backend
    python scripts/eval/translate_test.py

Requires .env with AZURE_OPENAI_* and GROQ_API_KEY set.
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from pathlib import Path

# Ensure UTF-8 output on Windows (avoids charmap errors for → ≥ ≤ etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Auto-discover backend/ (works regardless of how deep this script is nested)
_HERE = Path(__file__).resolve().parent
BACKEND_DIR = _HERE
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv

load_dotenv(BACKEND_DIR.parent / ".env")

# ── Parse SAS file into rough blocks (split on blank lines after run/quit) ──
import re as _re

from partition.models.enums import ConversionStatus, PartitionType, RiskLevel
from partition.models.partition_ir import PartitionIR
from partition.translation.translation_pipeline import TranslationPipeline

# Patterns that only appear in real SAS code (not plain prose comments)
_SAS_CODE_RE = _re.compile(
    r"^\s*(data\s+\w|proc\s+\w|%macro\b|%let\b|%do\b|%put\b|run\s*;|quit\s*;)",
    _re.IGNORECASE | _re.MULTILINE,
)


def _has_sas_code(text: str) -> bool:
    """Return True if the block contains at least one SAS statement (not just comments)."""
    return bool(_SAS_CODE_RE.search(text))


def parse_blocks(sas_path: Path) -> list[tuple[str, str]]:
    """Return list of (label, source_code) extracted from a SAS file.

    Supports two common section-marker styles:
      Style A (original torture_test.sas):
        /* ── 1. RETAIN + BY-group ─────────── */
      Style B (finance torture_test):
        /* 1. GLOBAL CONFIGURATION & ENVIRONMENT SETUP */
        /* N. ANY LABEL */

    Skips blocks that contain only comments (no actual SAS statements).
    Falls back to run/quit-boundary splitting if no section markers found.
    """
    text = sas_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Detect which marker style is present
    style_a = any(l.startswith("/* ──") and "──" in l for l in lines)
    style_b = any(_re.match(r"/\*\s*\d+\.", l.strip()) for l in lines)

    if not style_a and not style_b:
        # Fallback: split on RUN; / QUIT; boundaries
        return _split_by_run_quit(text)

    blocks: list[tuple[str, str]] = []
    current_label = "block_0"
    current_lines: list[str] = []

    for line in lines:
        is_marker = False

        if style_a and line.startswith("/* ──") and "──" in line:
            is_marker = True
            new_label = line.strip("/* ─").strip().rstrip(" */").strip()

        elif style_b:
            m = _re.match(r"/\*\s*(\d+\.\s*.+?)\s*\*/", line.strip())
            if m:
                is_marker = True
                new_label = m.group(1).strip()

        if is_marker:
            code = "\n".join(current_lines).strip()
            if code and _has_sas_code(code):
                blocks.append((current_label, code))
            current_label = new_label
            current_lines = []
        else:
            current_lines.append(line)

    code = "\n".join(current_lines).strip()
    if code and _has_sas_code(code):
        blocks.append((current_label, code))

    return blocks


def _split_by_run_quit(text: str) -> list[tuple[str, str]]:
    """Fallback: split SAS file on RUN; / QUIT; statement boundaries."""
    chunks = _re.split(r"(?i)\b(run|quit)\s*;", text)
    blocks = []
    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if chunk and _has_sas_code(chunk) and chunk.upper() not in ("RUN", "QUIT"):
            blocks.append((f"block_{i:02d}", chunk))
    return blocks


def make_partition(label: str, source: str, index: int) -> PartitionIR:
    """Wrap a raw SAS block into a PartitionIR for the pipeline."""
    # Heuristic: macros = MOD, SQL = MOD, everything else LOW
    if "%macro" in source.lower() or "proc sql" in source.lower():
        risk = RiskLevel.MODERATE
    elif "hash" in source.lower() or "first." in source.lower():
        risk = RiskLevel.HIGH
    else:
        risk = RiskLevel.LOW

    return PartitionIR(
        block_id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        partition_type=PartitionType.DATA_STEP,
        source_code=source,
        line_start=index * 30,
        line_end=(index + 1) * 30,
        risk_level=risk,
        # structural_only: syntax check only (no exec).
        # We don't have the actual input datasets here — exec would fail
        # on column names that depend on real data. Syntax validity is the
        # right check for a standalone translation test.
        metadata={"label": label, "test_coverage_type": "structural_only"},
    )


# ── ANSI colour helpers ──────────────────────────────────────────────────────

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"

STATUS_COLOUR = {
    ConversionStatus.SUCCESS: GREEN,
    ConversionStatus.PARTIAL: YELLOW,
    ConversionStatus.FAILED: RED,
    ConversionStatus.HUMAN_REVIEW: YELLOW,
}


async def run() -> None:
    # Accept optional path from CLI; default to built-in fixture
    if len(sys.argv) > 1:
        sas_path = Path(sys.argv[1]).resolve()
    else:
        sas_path = BACKEND_DIR / "tests" / "fixtures" / "torture_test.sas"
    if not sas_path.exists():
        print(f"{RED}SAS file not found: {sas_path}{RESET}")
        sys.exit(1)

    blocks = parse_blocks(sas_path)
    print(f"\n{CYAN}{'-' * 70}")
    print(f"  Codara translate_test - {len(blocks)} blocks from torture_test.sas")
    print(f"{'-' * 70}{RESET}\n")

    pipeline = TranslationPipeline(target_runtime="python", duckdb_path="data/analytics.duckdb")

    results = []
    total_start = time.monotonic()

    for i, (label, source) in enumerate(blocks):
        partition = make_partition(label, source, i)
        print(
            f"[{i + 1}/{len(blocks)}] {label[:55]:<55} risk={partition.risk_level.value:<10}",
            end="",
            flush=True,
        )
        t0 = time.monotonic()
        result = await pipeline.translate_partition(partition)
        elapsed = time.monotonic() - t0

        colour = STATUS_COLOUR.get(result.status, RESET)
        z3_info = f" z3={result.z3_status.value}" if result.z3_pattern else ""
        print(
            f"{colour}{result.status.value:<10}{RESET}"
            f" model={result.model_used:<20}"
            f" conf={result.llm_confidence:.2f}"
            f" {elapsed:.1f}s"
            f"{z3_info}"
        )
        results.append((label, result, elapsed))

    total_elapsed = time.monotonic() - total_start

    # Summary table
    print(f"\n{CYAN}{'-' * 70}")
    print("  Summary")
    print(f"{'-' * 70}{RESET}")

    success = sum(1 for _, r, _ in results if r.status == ConversionStatus.SUCCESS)
    partial = sum(1 for _, r, _ in results if r.status == ConversionStatus.PARTIAL)
    proved = sum(1 for _, r, _ in results if r.z3_status.value == "formal_proof")
    counterex = sum(1 for _, r, _ in results if r.z3_status.value == "counterexample")
    total = len(results)

    print(f"  Blocks translated : {total}")
    print(f"  SUCCESS           : {GREEN}{success}{RESET} ({success / total * 100:.0f}%)")
    print(f"  PARTIAL           : {YELLOW}{partial}{RESET} ({partial / total * 100:.0f}%)")
    print(f"  Z3 formal proofs  : {proved}")
    print(f"  Z3 counterexamples: {counterex}")
    print(f"  Total time        : {total_elapsed:.1f}s")
    print()

    # Save full translations to output/
    out_dir = BACKEND_DIR / "output" / "translate_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = sas_path.stem
    for i, (label, result, _) in enumerate(results):
        safe_label = _re.sub(r"[^\w]+", "_", label).strip("_")[:40]
        out_file = out_dir / f"{stem}_block{i + 1:02d}_{safe_label}.py"
        out_file.write_text(result.python_code, encoding="utf-8")
    merged_file = out_dir / f"{stem}_all.py"
    merged_file.write_text(
        "\n\n# "
        + "=" * 70
        + "\n\n".join(
            f"# Block {i + 1}: {label}\n# {'=' * 70}\n\n{result.python_code}"
            for i, (label, result, _) in enumerate(results)
        ),
        encoding="utf-8",
    )
    print(f"\n  Output saved to: {out_dir}/")

    # Print first few lines of each translation for inspection
    print(f"{CYAN}{'-' * 70}")
    print("  Translations preview (first 6 lines each)")
    print(f"{'-' * 70}{RESET}")
    for label, result, _ in results:
        preview = "\n".join(result.python_code.splitlines()[:6])
        colour = STATUS_COLOUR.get(result.status, RESET)
        print(f"\n{colour}[{label}]{RESET}")
        for line in preview.splitlines():
            print(f"  {line}")

    # Exit 1 if any block is PARTIAL (useful for CI)
    if partial > 0:
        print(f"\n{YELLOW}Warning: {partial} block(s) PARTIAL — check logs above.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run())
