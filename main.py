"""main.py — RAPTOR v2 SAS→Python Partition Pipeline entry point.

Usage:
    cd C:\\Users\\labou\\Desktop\\Stage
    venv\\Scripts\\python main.py --file path/to/file.sas
    venv\\Scripts\\python main.py --dir  path/to/sas/corpus/

Layers executed:
    L2-A : FileAnalysisAgent → CrossFileDependencyResolver → RegistryWriterAgent
    L2-B : StreamAgent → StateAgent
    L2-C : BoundaryDetectorAgent → PartitionBuilderAgent
    (L2-D, L3, L4 — Week 4+ : ComplexityAgent, TranslationAgent, etc.)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import structlog

# Ensure sas_converter/ is on the Python path when run from the repo root
_REPO_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(_REPO_ROOT / "sas_converter"))

from partition.logging_config import configure_logging  # noqa: E402


logger = structlog.get_logger()


async def process_file(sas_path: Path) -> None:
    """Run the full partitioning pipeline on a single SAS file."""
    from partition.db.sqlite_manager import SQLiteManager
    from partition.entry.file_analysis_agent import FileAnalysisAgent
    from partition.entry.cross_file_dep_resolver import CrossFileDependencyResolver
    from partition.entry.registry_writer_agent import RegistryWriterAgent
    from partition.streaming.pipeline import StreamingPipeline
    from partition.chunking.boundary_detector import BoundaryDetectorAgent
    from partition.chunking.partition_builder import PartitionBuilderAgent

    trace_id = uuid4()
    log = logger.bind(trace_id=str(trace_id), file=sas_path.name)

    # ── L2-A: Entry ──────────────────────────────────────────────────────────
    log.info("l2a_start")
    db     = SQLiteManager()
    faa    = FileAnalysisAgent(trace_id=trace_id)
    cfr    = CrossFileDependencyResolver(trace_id=trace_id)
    rwa    = RegistryWriterAgent(db=db, trace_id=trace_id)

    file_meta   = await faa.process(sas_path)
    cross_deps  = await cfr.process(file_meta)
    file_id     = await rwa.process(file_meta, cross_deps)
    log.info("l2a_complete", file_id=str(file_id))

    # ── L2-B: Streaming ──────────────────────────────────────────────────────
    log.info("l2b_start")
    pipeline         = StreamingPipeline(file_path=sas_path, file_id=file_id)
    chunks_with_states = await pipeline.run()
    log.info("l2b_complete", chunks=len(chunks_with_states))

    # ── L2-C: Chunking ───────────────────────────────────────────────────────
    log.info("l2c_start")
    bda        = BoundaryDetectorAgent(trace_id=trace_id)
    pba        = PartitionBuilderAgent(trace_id=trace_id)

    events     = await bda.process(chunks_with_states, file_id)
    partitions = await pba.process(events)
    log.info("l2c_complete", blocks=len(partitions))

    # ── Summary ──────────────────────────────────────────────────────────────
    type_counts: dict[str, int] = {}
    for p in partitions:
        key = p.partition_type.value
        type_counts[key] = type_counts.get(key, 0) + 1

    print(f"\n{'─'*50}")
    print(f"File   : {sas_path.name}")
    print(f"Blocks : {len(partitions)}")
    print("Types  :")
    for t, c in sorted(type_counts.items()):
        print(f"  {t:<28} {c:>4}")
    print(f"{'─'*50}\n")


async def main() -> None:
    configure_logging(level="INFO")

    parser = argparse.ArgumentParser(
        description="RAPTOR v2 — SAS → Python Partition Pipeline"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=Path, help="Single .sas file to process")
    group.add_argument("--dir",  type=Path, help="Directory of .sas files to process")
    args = parser.parse_args()

    if args.file:
        if not args.file.exists():
            print(f"[ERROR] File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        await process_file(args.file)
    else:
        sas_files = sorted(args.dir.glob("**/*.sas"))
        if not sas_files:
            print(f"[WARN] No .sas files found in: {args.dir}", file=sys.stderr)
            sys.exit(0)
        print(f"Processing {len(sas_files)} SAS file(s)...\n")
        for f in sas_files:
            try:
                await process_file(f)
            except Exception as exc:
                logger.error("file_failed", file=f.name, error=str(exc))


if __name__ == "__main__":
    asyncio.run(main())
