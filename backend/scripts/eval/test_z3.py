"""test_z3.py — standalone Z3 verification smoke-test.

Does NOT call the LLM. Instead it:
  1. Reads a SAS file (default: torture_test_finance.sas)
  2. Translates each block with the FULL pipeline (LLM + validate + Z3)
  3. Prints a detailed Z3 report: which pattern matched, PROVED/COUNTEREXAMPLE/UNKNOWN

Usage:
    cd backend
    python scripts/eval/test_z3.py
    python scripts/eval/test_z3.py path/to/file.sas

Exit code: 0 if no counterexamples found, 1 if any counterexamples detected.
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
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

import re as _re

from partition.models.enums import ConversionStatus, PartitionType, RiskLevel
from partition.models.partition_ir import PartitionIR
from partition.translation.translation_pipeline import TranslationPipeline
from partition.verification.z3_agent import Z3VerificationAgent

# ── colour helpers ────────────────────────────────────────────────────────────

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"

STATUS_COLOR = {
    "formal_proof": GREEN,
    "counterexample": RED,
    "unverifiable": YELLOW,
    "skipped": YELLOW,
}

CONV_COLOR = {
    ConversionStatus.SUCCESS: GREEN,
    ConversionStatus.PARTIAL: YELLOW,
    ConversionStatus.FAILED: RED,
    ConversionStatus.HUMAN_REVIEW: YELLOW,
}

# ── SAS code detection / block parsing (mirrors translate_test.py) ────────────

_SAS_CODE_RE = _re.compile(
    r"^\s*(data\s+\w|proc\s+\w|%macro\b|%let\b|%do\b|%put\b|run\s*;|quit\s*;)",
    _re.IGNORECASE | _re.MULTILINE,
)


def _has_sas_code(text: str) -> bool:
    return bool(_SAS_CODE_RE.search(text))


def parse_blocks(sas_path: Path) -> list[tuple[str, str]]:
    text = sas_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    style_a = any(l.startswith("/* ──") and "──" in l for l in lines)
    style_b = any(_re.match(r"/\*\s*\d+\.", l.strip()) for l in lines)

    if not style_a and not style_b:
        chunks = _re.split(r"(?i)\b(run|quit)\s*;", text)
        blocks = []
        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if chunk and _has_sas_code(chunk) and chunk.upper() not in ("RUN", "QUIT"):
                blocks.append((f"block_{i:02d}", chunk))
        return blocks

    blocks: list[tuple[str, str]] = []
    current_label = "block_0"
    current_lines: list[str] = []

    for line in lines:
        is_marker = False
        new_label = current_label

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


def make_partition(label: str, source: str, index: int) -> PartitionIR:
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
        metadata={"label": label, "test_coverage_type": "structural_only"},
    )


# ── main ──────────────────────────────────────────────────────────────────────


async def run() -> int:
    if len(sys.argv) > 1:
        sas_path = Path(sys.argv[1]).resolve()
    else:
        sas_path = BACKEND_DIR / "tests" / "fixtures" / "torture_test_finance.sas"

    if not sas_path.exists():
        print(f"{RED}File not found: {sas_path}{RESET}")
        return 1

    blocks = parse_blocks(sas_path)
    if not blocks:
        print(f"{YELLOW}No SAS blocks found in {sas_path.name}{RESET}")
        return 1

    print(f"\n{BOLD}{CYAN}{'='*72}")
    print("  Codara Z3 Verification Test")
    print(f"  File  : {sas_path.name}")
    print(f"  Blocks: {len(blocks)}")
    print(f"{'='*72}{RESET}\n")

    pipeline = TranslationPipeline(
        target_runtime="python",
        duckdb_path="data/analytics.duckdb",
    )

    rows = []
    t_all = time.monotonic()

    for i, (label, source) in enumerate(blocks):
        part = make_partition(label, source, i)
        short_label = label[:52]
        print(
            f"[{i+1:02d}/{len(blocks):02d}] {short_label:<52} " f"risk={part.risk_level.value:<10}",
            end="",
            flush=True,
        )
        t0 = time.monotonic()
        res = await pipeline.translate_partition(part)
        dt = time.monotonic() - t0

        z3_status = res.z3_status.value
        z3_color = STATUS_COLOR.get(z3_status, RESET)
        conv_color = CONV_COLOR.get(res.status, RESET)

        z3_tag = (
            f"{z3_color}[Z3:{res.z3_pattern or 'n/a'}={z3_status}]{RESET}"
            if res.z3_pattern
            else f"{YELLOW}[Z3:no_match]{RESET}"
        )

        print(
            f"{conv_color}{res.status.value:<8}{RESET} "
            f"conf={res.llm_confidence:.2f} "
            f"{dt:5.1f}s  "
            f"{z3_tag}"
        )

        if z3_status == "counterexample" and res.z3_status.value == "counterexample":
            # Print counterexample detail indented
            try:
                # z3_agent stores it on VerificationResult but pipeline stores
                # status on conversion — re-run Z3 agent directly to get details
                agent = Z3VerificationAgent()
                detail = agent.verify(source, res.python_code)
                if detail.counterexample:
                    for k, v in detail.counterexample.items():
                        v_str = str(v)
                        lines_v = v_str.splitlines()
                        print(f"        {RED}{k}{RESET}: {lines_v[0]}")
                        for extra in lines_v[1:]:
                            print(f"             {extra}")
            except Exception:
                pass

        rows.append((label, res, dt))

    elapsed = time.monotonic() - t_all

    # ── summary ───────────────────────────────────────────────────────────────
    success = sum(1 for _, r, _ in rows if r.status == ConversionStatus.SUCCESS)
    partial = sum(1 for _, r, _ in rows if r.status == ConversionStatus.PARTIAL)
    proved = sum(1 for _, r, _ in rows if r.z3_status.value == "formal_proof")
    counterexs = sum(1 for _, r, _ in rows if r.z3_status.value == "counterexample")
    unknown = sum(1 for _, r, _ in rows if r.z3_status.value == "unverifiable")
    no_match = sum(1 for _, r, _ in rows if not r.z3_pattern)
    total = len(rows)

    print(f"\n{BOLD}{CYAN}{'='*72}")
    print("  Z3 Verification Summary")
    print(f"{'='*72}{RESET}")
    print(f"  Blocks total          : {total}")
    print(f"  Translation SUCCESS   : {GREEN}{success}{RESET} / {YELLOW}{partial} PARTIAL{RESET}")
    print(f"  Z3 PROVED             : {GREEN}{proved}{RESET}")
    print(f"  Z3 COUNTEREXAMPLE     : {RED}{counterexs}{RESET}  ← re-translated at HIGH risk")
    print(f"  Z3 UNKNOWN (no proof) : {YELLOW}{unknown}{RESET}")
    print(f"  Z3 no pattern matched : {YELLOW}{no_match}{RESET}")
    print(f"  Total time            : {elapsed:.1f}s")
    print()

    # Per-block Z3 breakdown table
    print(f"  {'Block':<40} {'Conv':<8} {'Z3 pattern':<28} {'Z3 result'}")
    print(f"  {'-'*40} {'-'*8} {'-'*28} {'-'*15}")
    for label, res, _ in rows:
        z3c = STATUS_COLOR.get(res.z3_status.value, RESET)
        print(
            f"  {label[:40]:<40} "
            f"{res.status.value:<8} "
            f"{(res.z3_pattern or 'none'):<28} "
            f"{z3c}{res.z3_status.value}{RESET}"
        )
    print()

    # Save outputs
    out_dir = BACKEND_DIR / "output" / "z3_test"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = sas_path.stem
    for i, (label, res, _) in enumerate(rows):
        safe = _re.sub(r"[^\w]+", "_", label).strip("_")[:40]
        (out_dir / f"{stem}_block{i+1:02d}_{safe}.py").write_text(res.python_code, encoding="utf-8")
    print(f"  Output saved to: {out_dir}/\n")

    return 1 if counterexs > 0 else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
