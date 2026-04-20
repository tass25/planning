"""run_mis.py — Run MigrationInvariantSynthesizer on the gold corpus and print results.

Usage::
    python scripts/eval/run_mis.py
    python scripts/eval/run_mis.py --gold-dir path/to/gold_standard
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure backend package is on sys.path
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


def _load_benchmark_pairs(output_dir: Path) -> list[tuple[str, str]]:
    """Load (sas_code, python_code) pairs from benchmark JSON files in knowledge_base/output/."""
    import json

    pairs: list[tuple[str, str]] = []
    for f in sorted(output_dir.glob("benchmark_crossProvider_*.json")):
        try:
            d = json.loads(f.read_text("utf-8"))
            for r in d.get("results", []):
                sas = r.get("sas_code", "")
                py = r.get("python_code", "")
                if sas and py and r.get("equivalent", False):
                    pairs.append((sas, py))
        except Exception:
            pass
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MIS on gold-standard corpus")
    parser.add_argument(
        "--gold-dir",
        default=str(_root / "knowledge_base" / "gold_standard"),
        help="Path to gold_standard/ directory",
    )
    parser.add_argument(
        "--extra-dir",
        default=str(_root / "knowledge_base" / "output"),
        help="Path to benchmark output dir with crossProvider JSON pairs",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=200,
        help="Maximum number of corpus pairs to process (default: 200)",
    )
    args = parser.parse_args()

    from partition.invariant.invariant_synthesizer import MigrationInvariantSynthesizer

    extra_pairs = _load_benchmark_pairs(Path(args.extra_dir))
    print(f"\nRunning MIS on: {args.gold_dir}")
    print(f"Extra pairs   : {len(extra_pairs)} from {args.extra_dir}")
    print(f"Max pairs     : {args.max_pairs}\n")

    synth = MigrationInvariantSynthesizer(gold_standard_dir=args.gold_dir)
    inv_set = synth.synthesize(extra_pairs=extra_pairs, max_pairs=args.max_pairs)

    print(f"Pairs loaded  : {inv_set.n_pairs_total}")
    print(f"Observations  : {inv_set.n_observations}")
    print(f"Confirmed     : {len(inv_set.confirmed)}")
    print(f"Rejected      : {len(inv_set.rejected)}")
    print(f"Latency       : {inv_set.latency_ms:.0f}ms\n")

    print(inv_set.to_markdown_table())


if __name__ == "__main__":
    main()
