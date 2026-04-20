"""CLI: Expand Knowledge Base to a target pair count.

Identifies under-represented categories and failure modes,
then generates new SAS→Python pairs using the existing generate_kb_pairs pipeline.

Usage:
    python scripts/expand_kb.py --target 330 --batch_size 10
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

import lancedb
import structlog

log = structlog.get_logger(__name__)

# Categories to ensure coverage
TARGET_CATEGORIES = [
    "DATA_STEP",
    "PROC_MEANS",
    "PROC_FREQ",
    "PROC_SQL",
    "PROC_SORT",
    "PROC_TRANSPOSE",
    "PROC_REG",
    "PROC_LOGISTIC",
    "MACRO_DEF",
    "MACRO_CALL",
    "RETAIN",
    "ARRAY",
    "MERGE",
    "DATE_ARITHMETIC",
    "FORMAT",
    "MISSING_VALUE",
]


def _get_current_distribution(table) -> Counter:
    """Get current KB category distribution from LanceDB."""
    try:
        df = table.to_pandas()
        return Counter(df.get("partition_type", df.get("category", [])))
    except Exception:
        return Counter()


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand KB to target pair count.")
    parser.add_argument("--target", type=int, default=330, help="Target pair count")
    parser.add_argument("--batch_size", type=int, default=10, help="Pairs per batch")
    parser.add_argument("--kb_path", default="data/kb_lancedb", help="LanceDB path")
    parser.add_argument("--db_path", default="data/sas_converter.duckdb", help="DuckDB path")
    parser.add_argument("--dry_run", action="store_true", help="Show plan without generating")

    args = parser.parse_args()

    db = lancedb.connect(str(args.kb_path))
    table = db.open_table("kb_examples")

    dist = _get_current_distribution(table)
    current_total = sum(dist.values())
    needed = args.target - current_total

    if needed <= 0:
        print(f"KB already has {current_total} pairs (target: {args.target}). Nothing to do.")
        return 0

    print(f"Current KB: {current_total} pairs — need {needed} more to reach {args.target}")
    print()

    # Find under-represented categories
    avg_per_cat = current_total / max(len(TARGET_CATEGORIES), 1)
    gaps = []
    for cat in TARGET_CATEGORIES:
        count = dist.get(cat, 0)
        deficit = max(0, int(avg_per_cat) - count + 5)
        if deficit > 0:
            gaps.append((cat, count, deficit))

    gaps.sort(key=lambda g: g[2], reverse=True)

    print("Category gaps:")
    for cat, current, deficit in gaps[:10]:
        print(f"  {cat}: {current} pairs (deficit ~{deficit})")
    print()

    if args.dry_run:
        print("[DRY RUN] Would generate pairs for the above categories.")
        return 0

    # Generate pairs using existing pipeline
    from scripts.generate_kb_pairs import generate_batch

    generated = 0
    for cat, _, deficit in gaps:
        if generated >= needed:
            break
        batch = min(deficit, args.batch_size, needed - generated)
        print(f"Generating {batch} pairs for {cat}...")
        try:
            count = generate_batch(category=cat, count=batch)
            generated += count
            print(f"  → Generated {count} pairs")
        except Exception as e:
            log.warning("expand_kb_batch_failed", category=cat, error=str(e))
            print(f"  → Failed: {e}")

    print(f"\nExpansion complete: generated {generated} new pairs.")
    print(f"New total: {current_total + generated} / {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
