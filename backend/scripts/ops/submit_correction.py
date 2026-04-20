"""CLI: Submit a human correction for a conversion.

Usage:
    python scripts/submit_correction.py --conversion_id <uuid> --partition_id <uuid> \
        --sas_file original.sas --python_file corrected.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import lancedb
import structlog
from partition.retraining.feedback_ingestion import FeedbackIngestionAgent

log = structlog.get_logger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit a human correction into the KB feedback loop."
    )
    parser.add_argument("--conversion_id", required=True, help="UUID of original conversion")
    parser.add_argument("--partition_id", required=True, help="UUID of the partition")
    parser.add_argument("--sas_file", required=True, help="Path to original SAS file/snippet")
    parser.add_argument("--python_file", required=True, help="Path to corrected Python file")
    parser.add_argument("--db_path", default="data/sas_converter.duckdb", help="DuckDB path")
    parser.add_argument("--kb_path", default="data/kb_lancedb", help="LanceDB path")
    parser.add_argument("--confidence_threshold", type=float, default=0.85)

    args = parser.parse_args()

    sas_path = Path(args.sas_file)
    py_path = Path(args.python_file)

    if not sas_path.exists():
        print(f"ERROR: SAS file not found: {sas_path}")
        return 1
    if not py_path.exists():
        print(f"ERROR: Python file not found: {py_path}")
        return 1

    sas_code = sas_path.read_text(encoding="utf-8")
    corrected_python = py_path.read_text(encoding="utf-8")

    conn = duckdb.connect(str(args.db_path))
    db = lancedb.connect(str(args.kb_path))
    table = db.open_table("kb_examples")

    # Lazy imports for embedding + cross-verify
    from partition.kb.kb_writer import _embed_text
    from partition.translation.translation_agent import TranslationAgent

    ta = TranslationAgent()

    def cross_verify(sas: str, py: str) -> dict:
        import asyncio

        result = asyncio.run(ta._cross_verify(sas, py))
        return {"confidence": result.confidence}

    agent = FeedbackIngestionAgent(
        lancedb_table=table,
        embed_fn=_embed_text,
        cross_verifier_fn=cross_verify,
        duckdb_conn=conn,
        confidence_threshold=args.confidence_threshold,
    )

    result = agent.ingest(
        conversion_id=args.conversion_id,
        partition_id=args.partition_id,
        sas_code=sas_code,
        corrected_python=corrected_python,
    )

    if result["accepted"]:
        print(f"Correction ACCEPTED — new KB example: {result['new_kb_example_id']}")
    else:
        print(f"Correction REJECTED — {result['rejection_reason']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
