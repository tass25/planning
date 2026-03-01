"""boundary_benchmark.py — Evaluate BoundaryDetectorAgent against gold standard.

Usage:
    cd sas_converter
    ../venv/Scripts/python benchmark/boundary_benchmark.py

Target: boundary accuracy > 90% on the 721-block gold standard corpus.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

from partition.chunking.models import BlockBoundaryEvent


# ── Core evaluation function ──────────────────────────────────────────────────

def evaluate_boundary_accuracy(
    detected_events: list[BlockBoundaryEvent],
    gold_dir: str | Path,
    line_tolerance: int = 2,
) -> dict:
    """Compare detected BlockBoundaryEvents against gold standard annotations.

    A boundary is considered CORRECT when:
    - ``partition_type`` matches exactly.
    - ``line_start`` is within ±``line_tolerance`` lines.
    - ``line_end``   is within ±``line_tolerance`` lines.

    Args:
        detected_events:  All events from the pipeline run.
        gold_dir:         Directory containing ``*.gold.json`` files.
        line_tolerance:   Allowed line drift (default 2).

    Returns:
        dict with keys: accuracy, correct, total, target, passed, confusion.
    """
    total_gold   = 0
    correct      = 0
    type_confusion: dict[tuple[str, str], int] = {}

    for gold_file in Path(gold_dir).glob("*.gold.json"):
        with open(gold_file, encoding="utf-8") as f:
            gold = json.load(f)

        file_events = [
            e for e in detected_events
            if str(e.file_id) == gold.get("file_id")
        ]

        for gold_block in gold.get("blocks", []):
            total_gold += 1
            matched = False

            for event in file_events:
                type_match  = event.partition_type.value == gold_block["partition_type"]
                start_match = abs(event.line_start - gold_block["line_start"]) <= line_tolerance
                end_match   = abs(event.line_end   - gold_block["line_end"])   <= line_tolerance

                if type_match and start_match and end_match:
                    correct += 1
                    matched = True
                    break

            if not matched:
                # Record in confusion matrix: (predicted_type, gold_type)
                closest = min(
                    file_events,
                    key=lambda e: abs(e.line_start - gold_block["line_start"]),
                    default=None,
                )
                if closest:
                    key = (closest.partition_type.value, gold_block["partition_type"])
                    type_confusion[key] = type_confusion.get(key, 0) + 1

    accuracy = correct / total_gold if total_gold > 0 else 0.0

    return {
        "accuracy":  round(accuracy, 4),
        "correct":   correct,
        "total":     total_gold,
        "target":    0.90,
        "passed":    accuracy >= 0.90,
        "confusion": {str(k): v for k, v in type_confusion.items()},
    }


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def _run_pipeline_on_corpus(
    corpus_dir: Path,
    gold_dir: Path,
) -> list[BlockBoundaryEvent]:
    """Run BoundaryDetectorAgent on every .sas file in corpus_dir."""
    from uuid import uuid4
    from partition.chunking.boundary_detector import BoundaryDetectorAgent
    from partition.streaming.pipeline import StreamingPipeline  # type: ignore

    all_events: list[BlockBoundaryEvent] = []

    for sas_file in sorted(corpus_dir.glob("**/*.sas")):
        file_id = uuid4()
        try:
            pipeline  = StreamingPipeline(file_path=sas_file, file_id=file_id)
            pairs     = await pipeline.run()
            agent     = BoundaryDetectorAgent(trace_id=uuid4())
            events    = await agent.process(pairs, file_id)
            all_events.extend(events)
        except Exception as exc:
            print(f"  [WARN] {sas_file.name}: {exc}")

    return all_events


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="SAS boundary detection benchmark")
    parser.add_argument("--corpus",  default="knowledge_base/gold_standard", help="Directory of .sas files")
    parser.add_argument("--gold",    default="knowledge_base/gold_standard", help="Directory of .gold.json files")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus)
    gold_dir   = Path(args.gold)

    print(f"Running boundary benchmark on: {corpus_dir}")
    print(f"Gold standard from:            {gold_dir}\n")

    events = await _run_pipeline_on_corpus(corpus_dir, gold_dir)
    result = evaluate_boundary_accuracy(events, gold_dir)

    print("── Results ─────────────────────────────────")
    print(f"  Accuracy : {result['accuracy']:.1%}  (target ≥ 90%)")
    print(f"  Correct  : {result['correct']} / {result['total']}")
    print(f"  Status   : {'✅ PASSED' if result['passed'] else '❌ FAILED'}")

    if args.verbose and result["confusion"]:
        print("\n── Confusion (predicted → gold) ─────────────")
        for (pred, gold), count in sorted(result["confusion"].items(), key=lambda x: -x[1]):
            print(f"  {pred:25s} → {gold:25s}  ({count})")


if __name__ == "__main__":
    asyncio.run(main())
