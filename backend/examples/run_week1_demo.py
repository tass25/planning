"""Run all Week 1 agents against a SAS file and display results."""

import asyncio
import sys
import time
from pathlib import Path

# Ensure the sas_converter package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from partition.db.sqlite_manager import get_engine, init_db
from partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver
from partition.entry.data_lineage_extractor import DataLineageExtractor
from partition.entry.file_analysis_agent import FileAnalysisAgent
from partition.entry.registry_writer_agent import RegistryWriterAgent
from partition.utils.logging_config import configure_logging


async def main():
    sas_dir = Path(__file__).resolve().parent
    sas_file = sas_dir / "loan_decisions.sas"

    if not sas_file.exists():
        print(f"ERROR: {sas_file} not found")
        return

    # Use a temporary DB for this demo
    db_path = sas_dir / "demo_test.db"
    if db_path.exists():
        db_path.unlink()

    configure_logging()
    engine = get_engine(str(db_path))
    init_db(engine)

    separator = "=" * 70
    t_total = time.perf_counter()

    # ── 1. FileAnalysisAgent ──────────────────────────────────────────────
    print(f"\n{separator}")
    print("  AGENT 1 — FileAnalysisAgent")
    print(separator)
    agent1 = FileAnalysisAgent()
    t0 = time.perf_counter()
    files = await agent1.process(sas_dir)
    t1 = time.perf_counter()
    print(f"  ⏱  Elapsed: {t1 - t0:.4f}s")
    for fm in files:
        print(f"  File      : {fm.file_path}")
        print(f"  Encoding  : {fm.encoding}")
        print(f"  Lines     : {fm.line_count}")
        print(f"  SHA-256   : {fm.content_hash[:16]}...")
        print(f"  Size      : {fm.file_size_bytes} bytes")
        print(f"  Valid     : {fm.lark_valid}")
        if fm.lark_errors:
            for err in fm.lark_errors:
                print(f"  ⚠ Error   : {err}")

    # ── 2. RegistryWriterAgent ────────────────────────────────────────────
    print(f"\n{separator}")
    print("  AGENT 2 — RegistryWriterAgent")
    print(separator)
    agent2 = RegistryWriterAgent()
    t0 = time.perf_counter()
    reg_result = await agent2.process(files, engine)
    t1 = time.perf_counter()
    print(f"  ⏱  Elapsed: {t1 - t0:.4f}s")
    print(f"  Inserted  : {reg_result['inserted']}")
    print(f"  Skipped   : {reg_result['skipped']}")

    # ── 3. CrossFileDependencyResolver ────────────────────────────────────
    print(f"\n{separator}")
    print("  AGENT 3 — CrossFileDependencyResolver")
    print(separator)
    agent3 = CrossFileDependencyResolver()
    t0 = time.perf_counter()
    dep_result = await agent3.process(files, sas_dir, engine)
    t1 = time.perf_counter()
    print(f"  ⏱  Elapsed: {t1 - t0:.4f}s")
    print(f"  Total deps    : {dep_result['total']}")
    print(f"  Resolved      : {dep_result['resolved']}")
    print(f"  Unresolved    : {dep_result['unresolved']}")

    # ── 4. DataLineageExtractor ───────────────────────────────────────────
    print(f"\n{separator}")
    print("  AGENT 4 — DataLineageExtractor")
    print(separator)
    agent4 = DataLineageExtractor()
    t0 = time.perf_counter()
    lin_result = await agent4.process(files, engine)
    t1 = time.perf_counter()
    print(f"  ⏱  Elapsed: {t1 - t0:.4f}s")
    print(f"  Table reads   : {lin_result['total_reads']}")
    print(f"  Table writes  : {lin_result['total_writes']}")
    print(f"  Total edges   : {lin_result['total']}")

    # ── Show lineage details from DB ──────────────────────────────────────
    from partition.db.sqlite_manager import DataLineageRow, get_session

    session = get_session(engine)
    rows = session.query(DataLineageRow).all()
    if rows:
        print(f"\n  {'Type':<14} {'Direction':<13} {'Dataset':<30} {'Line':>5}")
        print(f"  {'-'*14} {'-'*13} {'-'*30} {'-'*5}")
        for r in rows:
            ds = r.source_dataset or r.target_dataset or "?"
            direction = "READ" if r.lineage_type == "TABLE_READ" else "WRITE"
            print(f"  {r.lineage_type:<14} {direction:<13} {ds:<30} {r.block_line_start or '':>5}")
    session.close()

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{separator}")
    print("  SUMMARY")
    print(separator)
    print(f"  SAS files discovered : {len(files)}")
    print(f"  Structurally valid   : {sum(1 for f in files if f.lark_valid)}")
    print(f"  Registry entries     : {reg_result['inserted']}")
    print(f"  Cross-file deps      : {dep_result['total']}")
    print(f"  Lineage edges        : {lin_result['total']}")
    print(f"  Database             : {db_path}")
    t_end = time.perf_counter()
    print(f"  Total elapsed        : {t_end - t_total:.4f}s")
    print()

    # Cleanup temp DB
    engine.dispose()
    db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
