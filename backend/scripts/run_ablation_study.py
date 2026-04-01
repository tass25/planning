"""End-to-end ablation study runner.

Steps
-----
1. Process every gold-standard SAS file through chunking + RAPTOR
   (no LLM needed for this — NomicEmbedder is local; summarizer uses heuristic fallback)
2. Write the RAPTOR nodes to LanceDB  (raptor_nodes table)
3. Build the flat index               (flat_nodes table)
4. Generate ablation queries from the collected partitions
5. Run the RAPTOR-vs-Flat retrieval comparison
6. Write results to ablation.db

Run from backend/:
    venv\\Scripts\\python.exe scripts\\run_ablation_study.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

# Load .env (best-effort — LLMs are not required for this script)
try:
    from dotenv import load_dotenv
    load_dotenv(_ROOT.parent / ".env", override=False)
except ImportError:
    pass

# Disable all LLM providers for the ablation study.
# The summarizer falls back to a fast heuristic (partition-type-based text) which
# is sufficient — the ablation measures embedding-space retrieval quality, not
# summary text quality. This reduces per-file time from ~2 min to ~5 sec.
os.environ.pop("AZURE_OPENAI_ENDPOINT", None)
os.environ.pop("AZURE_OPENAI_API_KEY", None)
os.environ.pop("GROQ_API_KEY", None)
os.environ.pop("GROQ_API_KEY_2", None)
os.environ.pop("GROQ_API_KEY_3", None)

import structlog

log = structlog.get_logger()

LANCEDB_PATH    = str(_ROOT / "lancedb_data")
ABLATION_DB     = str(_ROOT / "ablation.db")
GOLD_DIR        = _ROOT / "knowledge_base" / "gold_standard"
QUERIES_PER_FILE = 10


# ── Step helpers ──────────────────────────────────────────────────────────────


def _collect_sas_files() -> list[Path]:
    files = sorted(GOLD_DIR.glob("*.sas"))
    log.info("gold_files_found", count=len(files))
    return files


async def _process_file(sas_path: Path, embedder, clusterer, summarizer) -> tuple[list, list]:
    """Stream → chunk → RAPTOR one SAS file. Returns (partitions, raptor_nodes)."""
    import hashlib
    import uuid as _uuid
    from partition.models.file_metadata import FileMetadata
    from partition.streaming.pipeline import run_streaming_pipeline
    from partition.chunking.chunking_agent import ChunkingAgent
    from partition.raptor.tree_builder import RAPTORTreeBuilder

    # Build FileMetadata
    try:
        source = sas_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        log.warning("file_read_failed", path=str(sas_path), error=str(exc))
        return [], []

    file_id = _uuid.uuid4()
    content_hash = hashlib.sha256(source.encode()).hexdigest()
    file_meta = FileMetadata(
        file_id=file_id,
        file_path=str(sas_path),
        encoding="utf-8",
        content_hash=content_hash,
        file_size_bytes=len(source.encode()),
        line_count=source.count("\n") + 1,
        lark_valid=True,
    )

    # Stream
    try:
        chunks_with_states = await run_streaming_pipeline(file_meta)
    except Exception as exc:
        log.warning("streaming_failed", path=str(sas_path), error=str(exc))
        return [], []

    if not chunks_with_states:
        return [], []

    # Chunk
    try:
        chunker = ChunkingAgent()
        partitions = await chunker.process(chunks_with_states, file_id)
    except Exception as exc:
        log.warning("chunking_failed", path=str(sas_path), error=str(exc))
        return [], []

    if not partitions:
        return [], []

    # RAPTOR tree (heuristic fallback when no LLM)
    try:
        tb = RAPTORTreeBuilder(
            embedder=embedder,
            clusterer=clusterer,
            summarizer=summarizer,
        )
        nodes = tb.build_tree(
            partitions=partitions,
            file_id=str(file_id),
            macro_density=sum(1 for p in partitions if p.has_macros) / max(len(partitions), 1),
        )
    except Exception as exc:
        log.warning("raptor_failed", path=str(sas_path), error=str(exc))
        nodes = []

    return partitions, nodes


def _write_raptor_nodes(all_nodes) -> int:
    """Write all collected RAPTORNodes to LanceDB raptor_nodes table."""
    import lancedb as _lancedb
    from partition.raptor.lancedb_writer import RAPTORLanceDBWriter

    if not all_nodes:
        log.warning("no_raptor_nodes_to_write")
        return 0

    # Drop stale tables so each run starts from scratch (avoids UUID mismatch)
    _db = _lancedb.connect(LANCEDB_PATH)
    for _tbl in ("raptor_nodes", "flat_nodes"):
        if _tbl in _db.table_names():
            _db.drop_table(_tbl)

    writer = RAPTORLanceDBWriter(db_path=LANCEDB_PATH)
    # Write in batches of 100
    total = 0
    batch_size = 100
    for i in range(0, len(all_nodes), batch_size):
        batch = all_nodes[i : i + batch_size]
        total += writer.upsert_nodes(batch)
    log.info("raptor_nodes_written", total=total)
    return total


def _build_flat_index() -> dict:
    from partition.evaluation.flat_index import build_flat_index
    result = build_flat_index(
        lancedb_path=LANCEDB_PATH,
        raptor_table="raptor_nodes",
        flat_table="flat_nodes",
    )
    log.info("flat_index_built", **result)
    return result


_PTYPE_DEFAULT_TIER: dict[str, str] = {
    "MACRO_CONDITIONAL": "HIGH",
    "PROC_REG_LOGISTIC": "HIGH",
    "MACRO_BASIC": "MODERATE",
    "DATA_STEP_MERGE": "MODERATE",
    "DATA_STEP_ARRAY": "MODERATE",
    "DATA_STEP_FIRST_LAST": "MODERATE",
    "PROC_SQL": "MODERATE",
    "DATE_ARITHMETIC": "MODERATE",
}


def _generate_queries(all_partitions: list) -> list[dict]:
    from partition.evaluation.query_generator import generate_queries

    # Convert PartitionIR objects to dicts the generator understands
    part_dicts = []
    for p in all_partitions:
        ptype = getattr(p, "partition_type", None)
        ptype_str = ptype.value if hasattr(ptype, "value") else str(ptype)

        risk = getattr(p, "risk_level", None)
        risk_val = risk.value if hasattr(risk, "value") else None
        if risk_val and risk_val != "UNCERTAIN":
            tier = {"LOW": "LOW", "MOD": "MODERATE",
                    "MODERATE": "MODERATE", "HIGH": "HIGH"}.get(risk_val, "LOW")
        else:
            # ComplexityAgent not run in ablation — infer from partition type.
            tier = _PTYPE_DEFAULT_TIER.get(ptype_str, "LOW")

        source_code = getattr(p, "source_code", "") or ""

        part_dicts.append({
            "partition_id":   str(getattr(p, "block_id", "")),
            "block_id":       str(getattr(p, "block_id", "")),
            "source_file_id": str(getattr(p, "file_id", "")),
            "file_id":        str(getattr(p, "file_id", "")),
            "partition_type": ptype_str,
            "complexity_tier": tier,
            "source_code":    source_code[:500],
        })

    queries = generate_queries(part_dicts, n_per_file=QUERIES_PER_FILE)
    log.info("queries_generated", count=len(queries))
    return queries


def _run_ablation(queries: list[dict], embedder) -> dict:
    from partition.evaluation.ablation_runner import AblationRunner

    embed_fn = lambda text: embedder.embed_query(text)

    runner = AblationRunner(
        lancedb_path=LANCEDB_PATH,
        duckdb_path=ABLATION_DB,
        embed_fn=embed_fn,
        raptor_table="raptor_nodes",
        flat_table="flat_nodes",
        k=5,
    )
    summary = runner.run(queries)
    return summary


# ── Main ──────────────────────────────────────────────────────────────────────


async def main():
    from partition.raptor.embedder import NomicEmbedder
    from partition.raptor.clustering import GMMClusterer
    from partition.raptor.summarizer import ClusterSummarizer

    log.info("ablation_study_start", lancedb=LANCEDB_PATH, duckdb=ABLATION_DB)

    # Load shared components once
    log.info("loading_embedder")
    embedder  = NomicEmbedder(device="cpu")
    clusterer = GMMClusterer()
    summarizer = ClusterSummarizer()

    sas_files = _collect_sas_files()
    if not sas_files:
        log.error("no_sas_files_found", dir=str(GOLD_DIR))
        sys.exit(1)

    all_partitions = []
    all_nodes      = []

    # ── Step 1: process each SAS file ────────────────────────────────────────
    for i, sas_path in enumerate(sas_files, 1):
        log.info("processing_file", i=i, total=len(sas_files), name=sas_path.name)
        partitions, nodes = await _process_file(
            sas_path, embedder, clusterer, summarizer
        )
        all_partitions.extend(partitions)
        all_nodes.extend(nodes)
        log.info("file_done", name=sas_path.name,
                 partitions=len(partitions), nodes=len(nodes))

    log.info("all_files_processed",
             total_partitions=len(all_partitions),
             total_raptor_nodes=len(all_nodes))

    if not all_nodes:
        log.error("no_raptor_nodes_produced — check chunking pipeline")
        sys.exit(1)

    # ── Step 2: write RAPTOR nodes to LanceDB ────────────────────────────────
    log.info("step2_write_raptor_nodes")
    _write_raptor_nodes(all_nodes)

    # ── Step 3: build flat index ──────────────────────────────────────────────
    log.info("step3_build_flat_index")
    flat_result = _build_flat_index()
    if flat_result.get("flat_node_count", 0) == 0:
        log.error("flat_index_empty — no level-0 RAPTOR nodes found")
        sys.exit(1)

    # ── Step 4: generate queries ──────────────────────────────────────────────
    log.info("step4_generate_queries")
    queries = _generate_queries(all_partitions)
    if not queries:
        log.error("no_queries_generated")
        sys.exit(1)

    # ── Step 5: run ablation ──────────────────────────────────────────────────
    log.info("step5_run_ablation", n_queries=len(queries))
    summary = _run_ablation(queries, embedder)

    # ── Report ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("ABLATION STUDY RESULTS")
    print("=" * 60)
    for idx in ("raptor", "flat"):
        if idx in summary:
            s = summary[idx]
            print(f"\n{idx.upper()}")
            print(f"  hit@5       : {s['hit_rate_at_5']:.4f}")
            print(f"  MRR         : {s['mrr']:.4f}")
            print(f"  avg latency : {s['avg_latency_ms']:.1f} ms")
            print(f"  queries     : {s['n_queries']}")
            for tier, ts in s.get("by_complexity", {}).items():
                print(f"    {tier}: hit@5={ts['hit_rate']:.4f}  n={ts['count']}")
    if "advantage" in summary:
        adv = summary["advantage"]
        print(f"\nRAPTOR advantage (hit@5 delta) : {adv['hit_rate_delta']:+.4f}")
        for tier in ("MODERATE", "HIGH"):
            k = f"{tier}_hit_rate_delta"
            if k in adv:
                print(f"  {tier}: {adv[k]:+.4f}")
    print("\nResults written to:", ABLATION_DB)
    print("=" * 60)

    # Warn if targets not met
    raptor_hr = summary.get("raptor", {}).get("hit_rate_at_5", 0)
    adv_mod_high = summary.get("advantage", {}).get("MODERATE_hit_rate_delta", 0)
    adv_high     = summary.get("advantage", {}).get("HIGH_hit_rate_delta", 0)
    combined_adv = (adv_mod_high + adv_high) / 2 if (adv_mod_high or adv_high) else 0

    if raptor_hr < 0.82:
        print(f"⚠  RAPTOR hit@5 {raptor_hr:.4f} < 0.82 target")
    if combined_adv < 0.10:
        print(f"⚠  RAPTOR MOD/HIGH advantage {combined_adv:.4f} < 0.10 target")


if __name__ == "__main__":
    asyncio.run(main())
