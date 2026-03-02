"""
Demo: run the full L2 pipeline on examples/test_input.sas and print detected blocks.

Usage (from sas_converter/):
    $env:PYTHONPATH="$PWD"
    $env:LLM_PROVIDER="none"
    $env:PYTHONIOENCODING="utf-8"
    ../venv/Scripts/python examples/demo_pipeline.py
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

# ── Setup path ────────────────────────────────────────────────
import sys
# examples/ is one level inside sas_converter/ — add sas_converter/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline
from partition.chunking.boundary_detector import BoundaryDetectorAgent
from partition.chunking.partition_builder import PartitionBuilderAgent
from partition.complexity.complexity_agent import ComplexityAgent
from partition.complexity.strategy_agent import StrategyAgent


SAS_FILE = Path(__file__).parent / "test_input.sas"


async def main() -> None:
    print("=" * 65)
    print("  SAS Converter — L2 Pipeline Demo")
    print(f"  File: {SAS_FILE.name}")
    print("=" * 65)

    # ── 1. File metadata ──────────────────────────────────────
    file_id = uuid4()
    sas_text = SAS_FILE.read_text(encoding="utf-8")
    file_meta = FileMetadata(
        file_id=file_id,
        file_path=str(SAS_FILE),
        encoding="utf-8",
        content_hash="demo",
        file_size_bytes=SAS_FILE.stat().st_size,
        line_count=len(sas_text.splitlines()),
        lark_valid=True,
    )

    # ── 2. Streaming: StreamAgent → StateAgent ────────────────
    print("\n[1/4] Streaming & state detection …")
    chunks_with_states = await run_streaming_pipeline(file_meta)
    total_lines = max(c.line_number for c, _ in chunks_with_states)
    print(f"      {total_lines} lines streamed, "
          f"{len(chunks_with_states)} chunks produced")

    # ── 3. BoundaryDetectorAgent (no LLM) ────────────────────
    print("[2/4] Boundary detection (deterministic, no LLM) …")
    os.environ.setdefault("LLM_PROVIDER", "none")   # skip LLM call
    detector = BoundaryDetectorAgent()
    events = await detector.process(chunks_with_states, file_id)
    print(f"      {len(events)} boundary events detected")

    # ── 4. PartitionBuilderAgent ──────────────────────────────
    print("[3/4] Building PartitionIR objects …")
    builder = PartitionBuilderAgent()
    partitions = await builder.process(events)
    print(f"      {len(partitions)} PartitionIR objects built")

    # ── 5. ComplexityAgent (rule-based, no training needed) ───
    print("[4/4] Complexity scoring + Strategy routing …")
    complexity = ComplexityAgent()
    partitions = await complexity.process(partitions)
    strategy = StrategyAgent()
    partitions = await strategy.process(partitions)

    # ── Results ───────────────────────────────────────────────
    print()
    print("=" * 65)
    print(f"  DETECTED BLOCKS  ({len(partitions)} total)")
    print("=" * 65)
    print(f"  {'#':<3} {'Type':<22} {'Lines':>12} {'Risk':<10} {'Strategy'}")
    print(f"  {'-'*3} {'-'*22} {'-'*12} {'-'*10} {'-'*22}")

    for i, p in enumerate(partitions, 1):
        ptype  = p.partition_type.value
        lines  = f"{p.line_start}–{p.line_end}"
        risk   = p.risk_level.value if p.risk_level else "?"
        strat  = p.metadata.get("strategy", "—")
        conf   = p.metadata.get("complexity_confidence", 0.0)
        print(f"  {i:<3} {ptype:<22} {lines:>12}   {risk:<10} {strat}  (conf={conf:.2f})")

    # ── Source code snippet per block ─────────────────────────
    sas_lines = SAS_FILE.read_text(encoding="utf-8").splitlines()
    print()
    print("=" * 65)
    print("  BLOCK CONTENT PREVIEW")
    print("=" * 65)
    for i, p in enumerate(partitions, 1):
        ptype = p.partition_type.value
        start, end = p.line_start - 1, p.line_end          # 0-indexed slice
        block_lines = sas_lines[start:end]
        print(f"\n  ── Block {i}: {ptype} (lines {p.line_start}–{p.line_end}) ──")
        for ln in block_lines:
            print(f"    {ln}")

    # ── EXPECTED gold annotation ──────────────────────────────
    print()
    print("=" * 65)
    print("  EXPECTED GOLD ANNOTATION")
    print("=" * 65)
    gold = [
        ("DATA_STEP",   1,  12, "sales – DATA + DATALINES + RUN"),
        ("DATA_STEP",  14,  19, "sales_updated – IF/ELSE + RUN"),
        ("PROC_BLOCK", 21,  28, "PROC MEANS aggregation + RUN"),
        ("SQL_BLOCK",  30,  36, "PROC SQL filter + QUIT"),
    ]
    print(f"  {'#':<3} {'Type':<22} {'Lines':>12}   {'Description'}")
    print(f"  {'-'*3} {'-'*22} {'-'*12}   {'-'*30}")
    for i, (t, s, e, desc) in enumerate(gold, 1):
        print(f"  {i:<3} {t:<22} {s}–{e:>3}          {desc}")

    # ── Match summary ─────────────────────────────────────────
    print()
    print("=" * 65)
    print("  MATCH SUMMARY (tolerance ±2 lines)")
    print("=" * 65)
    TOLS = 2
    matched = 0
    for (gt, gs, ge, _) in gold:
        hit = any(
            p.partition_type.value == gt
            and abs(p.line_start - gs) <= TOLS
            and abs(p.line_end   - ge) <= TOLS
            for p in partitions
        )
        mark = "✓" if hit else "✗"
        if hit:
            matched += 1
        print(f"  {mark}  {gt} L{gs}–{ge}")

    pct = matched / len(gold) * 100
    print(f"\n  Score: {matched}/{len(gold)}  ({pct:.0f}%)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
