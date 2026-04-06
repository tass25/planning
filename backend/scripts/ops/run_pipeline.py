"""CLI entry point for the SAS partition pipeline.

Usage::

    python scripts/run_pipeline.py data/sas_files/*.sas --target python
    python scripts/run_pipeline.py file1.sas file2.sas --redis redis://localhost:6379/1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from repo root (Stage/.env)
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# Ensure backend/ is on the Python path
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from partition.db.duckdb_manager import init_all_duckdb_tables  # noqa: E402
from partition.orchestration.orchestrator import PartitionOrchestrator  # noqa: E402
from partition.logging_config import configure_logging  # noqa: E402

configure_logging()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SAS -> Python Partition Pipeline (Week 8 Orchestrator)"
    )
    parser.add_argument("files", nargs="+", help="SAS file paths or directories")
    parser.add_argument(
        "--target",
        choices=["python"],
        default="python",
        help="Target runtime (default: python)",
    )
    parser.add_argument(
        "--redis",
        default="redis://localhost:6379/0",
        help="Redis URL for checkpointing",
    )
    parser.add_argument(
        "--duckdb",
        default="analytics.duckdb",
        help="DuckDB path for audit logs",
    )
    args = parser.parse_args()

    # Initialize analytics DB
    init_all_duckdb_tables(args.duckdb)

    # Create orchestrator
    orchestrator = PartitionOrchestrator(
        redis_url=args.redis,
        duckdb_path=args.duckdb,
        target_runtime=args.target,
    )

    # Run
    result = asyncio.run(orchestrator.run(args.files))

    # Summary
    print(f"\n{'=' * 60}")
    print("Pipeline Complete")
    print(f"  Files processed : {len(result.get('input_paths', []))}")
    print(f"  File IDs        : {len(result.get('file_ids', []))}")
    print(f"  Partitions      : {result.get('partition_count', 0)}")
    print(f"  Persisted       : {result.get('persisted_count', 0)}")
    print(f"  SCC groups      : {len(result.get('scc_groups', []))}")
    print(f"  Max hop         : {result.get('max_hop', 0)}")
    print(f"  RAPTOR nodes    : {len(result.get('raptor_nodes', []))}")
    print(f"  Translations    : {len(result.get('conversion_results', []))}")
    print(f"  Validated       : {result.get('validation_passed', 0)}")
    print(f"  Merged files    : {len(result.get('merge_results', []))}")
    print(f"  Errors          : {len(result.get('errors', []))}")
    print(f"  Warnings        : {len(result.get('warnings', []))}")
    print(f"{'=' * 60}")

    errors = result.get("errors", [])
    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  [X] {e}")

    warnings = result.get("warnings", [])
    if warnings:
        print("\nWarnings:")
        for w in warnings[:10]:
            print(f"  [!] {w}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
