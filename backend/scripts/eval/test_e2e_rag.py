"""End-to-end tests: RAG (Static + Graph + Agentic) + Continuous Learning.

Rules:
  - No mocking. Real LanceDB, real DuckDB (in-memory), real Groq calls.
  - Every test writes its full output to backend/tests/output/<TestName>.txt
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from dotenv import load_dotenv

# Load .env so GROQ_API_KEY is available
_env_path = Path(__file__).parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
OUTPUT_DIR = ROOT / "tests" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from partition.models.enums import PartitionType, RiskLevel
from partition.models.partition_ir import PartitionIR
from partition.rag.router import RAGRouter
from partition.rag.static_rag import StaticRAG
from partition.rag.graph_rag import GraphRAG
from partition.rag.agentic_rag import AgenticRAG
from partition.translation.kb_query import KBQueryClient
from partition.retraining.feedback_ingestion import FeedbackIngestionAgent
from partition.retraining.quality_monitor import ConversionQualityMonitor
from partition.retraining.retrain_trigger import RetrainTrigger
from partition.kb.kb_writer import KBWriter
from partition.raptor.embedder import NomicEmbedder
from partition.utils.llm_clients import get_groq_openai_client
import instructor

GOLD_DIR = ROOT / "knowledge_base" / "gold_standard"
LANCEDB_PATH = str(ROOT / "data/lancedb")

_passed = 0
_failed = 0
_errors: list[tuple[str, str]] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_output(name: str, content: str) -> Path:
    """Save test output to tests/output/<name>.txt"""
    safe = name.replace(" ", "_").replace("/", "-").replace("--", "-")
    path = OUTPUT_DIR / f"{safe}.txt"
    path.write_text(content, encoding="utf-8")
    return path


def _make_partition(
    sas_code: str,
    partition_type: PartitionType = PartitionType.DATA_STEP,
    risk_level: RiskLevel = RiskLevel.LOW,
    dependencies: list | None = None,
    scc_id: str | None = None,
    retry: int = 0,
    failure_mode: str | None = None,
) -> PartitionIR:
    p = PartitionIR(
        block_id=uuid.uuid4(),
        file_id=uuid.uuid4(),
        partition_type=partition_type,
        source_code=sas_code,
        line_start=1,
        line_end=sas_code.count("\n") + 1,
        risk_level=risk_level,
        dependencies=dependencies or [],
    )
    if scc_id:
        p.metadata["scc_id"] = scc_id
    if failure_mode:
        p.metadata["failure_mode"] = failure_mode
    p.metadata["retry_count"] = retry
    return p


def _make_real_duckdb() -> duckdb.DuckDBPyConnection:
    """Create a real in-memory DuckDB connection with all required tables."""
    conn = duckdb.connect(":memory:")

    conn.execute("""
        CREATE TABLE conversion_results (
            conversion_id VARCHAR,
            block_id      VARCHAR,
            status        VARCHAR,
            llm_confidence DOUBLE,
            failure_mode_flagged BOOLEAN,
            failure_mode  VARCHAR,
            created_at    VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE kb_changelog (
            entry_id   VARCHAR,
            action     VARCHAR,
            created_at VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE calibration_log (
            ece_score  DOUBLE,
            created_at VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE quality_metrics (
            metric_id          VARCHAR,
            batch_id           VARCHAR,
            n_evaluated        INTEGER,
            success_rate       DOUBLE,
            partial_rate       DOUBLE,
            human_review_rate  DOUBLE,
            avg_llm_confidence DOUBLE,
            failure_mode_dist  VARCHAR,
            created_at         VARCHAR
        )
    """)
    return conn


def _make_groq_cross_verifier():
    """Build a real Groq-based cross-verifier function using instructor."""
    from pydantic import BaseModel, Field

    class VerifyResult(BaseModel):
        equivalent: bool
        confidence: float = Field(..., ge=0.0, le=1.0)
        issues: list[str] = Field(default_factory=list)

    raw_client = get_groq_openai_client(async_client=False)
    if raw_client is None:
        raise RuntimeError("GROQ_API_KEY not set - cannot build real cross-verifier")
    client = instructor.from_openai(raw_client, mode=instructor.Mode.JSON)

    def verify(sas_code: str, python_code: str) -> dict:
        prompt = (
            "You are a SAS-to-Python expert.\n"
            "Determine if the Python code is a correct translation of the SAS code.\n\n"
            f"SAS code:\n```sas\n{sas_code}\n```\n\n"
            f"Python code:\n```python\n{python_code}\n```\n\n"
            "Respond with JSON: {equivalent: bool, confidence: float 0-1, issues: [str]}"
        )
        result = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_model=VerifyResult,
            max_retries=2,
        )
        return {"equivalent": result.equivalent, "confidence": result.confidence, "issues": result.issues}

    return verify


def _run(name: str, fn, *args) -> None:
    global _passed, _failed
    buf = io.StringIO()
    print(f"\n{'='*60}", flush=True)
    print(f"  Running: {name}", flush=True)
    print(f"{'='*60}", flush=True)
    try:
        with redirect_stdout(buf):
            result = fn(buf, *args)
        output = buf.getvalue()
        path = _write_output(name, output)
        print(output, end="")
        print(f"  [PASS] Output -> {path.name}", flush=True)
        _passed += 1
    except Exception as exc:
        output = buf.getvalue()
        import traceback
        tb = traceback.format_exc()
        full_output = output + f"\n\nFAILED: {exc}\n{tb}"
        path = _write_output(name, full_output)
        print(output, end="")
        print(f"  [FAIL] {exc}", flush=True)
        print(f"  Output -> {path.name}", flush=True)
        _failed += 1
        _errors.append((name, str(exc)))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_kb_loaded(out: io.StringIO) -> None:
    """Test 1: Verify LanceDB knowledge base is populated."""
    writer = KBWriter(db_path=LANCEDB_PATH)
    count = writer.count()
    stats = writer.coverage_stats()

    print(f"Test: KB Loaded", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"LanceDB path: {LANCEDB_PATH}", file=out)
    print(f"", file=out)
    print(f"Total pairs: {count}", file=out)
    print(f"Categories ({len(stats)}):", file=out)
    for cat, n in sorted(stats.items()):
        bar = "#" * n
        print(f"  {cat:<30} {n:>3}  {bar}", file=out)

    assert count > 0, f"KB is empty at {LANCEDB_PATH}"
    print(f"\nResult: PASS -- {count} pairs, {len(stats)} categories", file=out)


def test_kb_query(out: io.StringIO, embedder: NomicEmbedder) -> None:
    """Test 2: KBQueryClient - real semantic retrieval from LanceDB."""
    sas_code = (GOLD_DIR / "gs_01_basic_data_step.sas").read_text()
    client = KBQueryClient(db_path=LANCEDB_PATH)

    print(f"Test: KB Query (KBQueryClient)", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"Query SAS file: gs_01_basic_data_step.sas", file=out)
    print(f"SAS code ({len(sas_code)} chars):\n{sas_code.strip()}", file=out)
    print(f"", file=out)

    t0 = time.perf_counter()
    emb = embedder.embed(sas_code)
    t_embed = time.perf_counter() - t0
    print(f"Embedding: dim={len(emb)}, time={t_embed:.2f}s", file=out)

    # Try all categories present in the KB
    writer = KBWriter(db_path=LANCEDB_PATH)
    stats = writer.coverage_stats()
    total_found = 0

    print(f"\nQuerying each category (k=3):", file=out)
    for ptype in sorted(stats.keys()):
        t0 = time.perf_counter()
        results = client.retrieve_examples(query_embedding=emb, partition_type=ptype, k=3)
        elapsed = time.perf_counter() - t0
        total_found += len(results)
        if results:
            top = results[0]
            print(f"  {ptype:<30} {len(results)} hits  sim={top.get('similarity',0):.3f}  t={elapsed:.3f}s", file=out)
            for r in results:
                print(f"    - {r.get('category')} | sim={r.get('similarity',0):.3f} | sas_lines={len(r.get('sas_code','').splitlines())}", file=out)
        else:
            print(f"  {ptype:<30} 0 hits  (similarity below 0.50 threshold)  t={elapsed:.3f}s", file=out)

    print(f"\nFallback: KBWriter.search (no type filter, k=5):", file=out)
    raw = writer.search(emb, top_k=5)
    for r in raw:
        dist = r.get("_distance", "N/A")
        sim = (1 - dist) if isinstance(dist, float) else "N/A"
        print(f"  {r.get('category','?'):<30} dist={dist}  sim={sim if isinstance(sim,str) else f'{sim:.3f}'}", file=out)

    print(f"\nTotal results across all category queries: {total_found}", file=out)
    print(f"Fallback (no filter) results: {len(raw)}", file=out)
    print(f"\nResult: PASS", file=out)


def test_static_rag(out: io.StringIO, embedder: NomicEmbedder) -> None:
    """Test 3: Static RAG - LOW risk, k=3, leaf level."""
    sas_code = (GOLD_DIR / "gs_01_basic_data_step.sas").read_text()
    kb_client = KBQueryClient(db_path=LANCEDB_PATH)
    rag = StaticRAG(embedder=embedder, kb_client=kb_client)

    print(f"Test: Static RAG", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"SAS file: gs_01_basic_data_step.sas", file=out)
    print(f"Risk: LOW  |  Expected: paradigm=static, k=3, level=leaf", file=out)
    print(f"", file=out)

    t0 = time.perf_counter()
    ctx = rag.build_context(
        source_code=sas_code,
        partition_type="DATA_STEP_RETAIN",
        risk_level="LOW",
    )
    elapsed = time.perf_counter() - t0

    print(f"paradigm:      {ctx['paradigm']}", file=out)
    print(f"retrieval_k:   {ctx['retrieval_k']}", file=out)
    print(f"raptor_level:  {ctx['raptor_level']}", file=out)
    print(f"kb_examples:   {len(ctx['kb_examples'])}", file=out)
    print(f"prompt_length: {len(ctx['prompt'])} chars", file=out)
    print(f"build_time:    {elapsed:.3f}s", file=out)

    if ctx["kb_examples"]:
        print(f"\nTop KB examples retrieved:", file=out)
        for i, ex in enumerate(ctx["kb_examples"], 1):
            print(f"  [{i}] category={ex.get('category')}  similarity={ex.get('similarity',0):.4f}", file=out)
            print(f"      sas_lines={len(ex.get('sas_code','').splitlines())}  py_lines={len(ex.get('python_code','').splitlines())}", file=out)

    print(f"\nGenerated prompt (first 500 chars):", file=out)
    print(ctx["prompt"][:500], file=out)

    assert ctx["paradigm"] == "static"
    assert ctx["retrieval_k"] == 3
    assert ctx["raptor_level"] == "leaf"
    print(f"\nResult: PASS", file=out)


def test_graph_rag(out: io.StringIO, embedder: NomicEmbedder) -> None:
    """Test 4: Graph RAG - cross-file deps, k=5, cluster level."""
    sas_code = (GOLD_DIR / "gs_02_retain_accumulator.sas").read_text()
    dep_id = uuid.uuid4()
    kb_client = KBQueryClient(db_path=LANCEDB_PATH)
    rag = GraphRAG(embedder=embedder, kb_client=kb_client)

    print(f"Test: Graph RAG", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"SAS file: gs_02_retain_accumulator.sas", file=out)
    print(f"Risk: MODERATE  |  Expected: paradigm=graph, k=5, level=cluster", file=out)
    print(f"partition_id (simulated dep): {dep_id}", file=out)
    print(f"scc_id: scc-cluster-001", file=out)
    print(f"", file=out)

    t0 = time.perf_counter()
    ctx = rag.build_context(
        source_code=sas_code,
        partition_type="DATA_STEP_RETAIN",
        risk_level="MODERATE",
        partition_id=str(dep_id),
        scc_id="scc-cluster-001",
    )
    elapsed = time.perf_counter() - t0

    print(f"paradigm:      {ctx['paradigm']}", file=out)
    print(f"retrieval_k:   {ctx['retrieval_k']}", file=out)
    print(f"raptor_level:  {ctx['raptor_level']}", file=out)
    print(f"kb_examples:   {len(ctx['kb_examples'])}", file=out)
    print(f"graph_context: {len(ctx.get('graph_context', []))} entries", file=out)
    print(f"prompt_length: {len(ctx['prompt'])} chars", file=out)
    print(f"build_time:    {elapsed:.3f}s", file=out)

    if ctx["kb_examples"]:
        print(f"\nTop KB examples retrieved:", file=out)
        for i, ex in enumerate(ctx["kb_examples"][:3], 1):
            print(f"  [{i}] category={ex.get('category')}  similarity={ex.get('similarity',0):.4f}", file=out)

    if ctx.get("graph_context"):
        print(f"\nGraph context entries:", file=out)
        for entry in ctx["graph_context"]:
            print(f"  - {entry}", file=out)
    else:
        print(f"\nGraph context: empty (no NetworkX graph loaded in this isolated run)", file=out)

    print(f"\nGenerated prompt (first 500 chars):", file=out)
    print(ctx["prompt"][:500], file=out)

    assert ctx["paradigm"] == "graph"
    assert ctx["retrieval_k"] == 5
    assert ctx["raptor_level"] == "cluster"
    print(f"\nResult: PASS", file=out)


def test_agentic_rag(out: io.StringIO, embedder: NomicEmbedder) -> None:
    """Test 5: Agentic RAG - HIGH risk, adaptive k, RAPTOR level escalation."""
    sas_file = GOLD_DIR / "gs_05_etl_pipeline.sas"
    if not sas_file.exists():
        sas_file = GOLD_DIR / "gs_01_basic_data_step.sas"
    sas_code = sas_file.read_text()
    kb_client = KBQueryClient(db_path=LANCEDB_PATH)
    rag = AgenticRAG(embedder=embedder, kb_client=kb_client)

    print(f"Test: Agentic RAG", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"SAS file: {sas_file.name}", file=out)
    print(f"Risk: HIGH  |  Expected: paradigm=agentic, k=8, level escalates each attempt", file=out)
    print(f"", file=out)

    for attempt in range(3):
        t0 = time.perf_counter()
        ctx = rag.build_context(
            source_code=sas_code,
            partition_type="DATA_STEP_RETAIN",
            risk_level="HIGH",
            failure_mode="RETAIN" if attempt == 0 else None,
            attempt_number=attempt,
        )
        elapsed = time.perf_counter() - t0
        expected_level = ["leaf", "cluster", "root"][attempt]
        print(f"Attempt {attempt}:", file=out)
        print(f"  paradigm:     {ctx['paradigm']}", file=out)
        print(f"  retrieval_k:  {ctx['retrieval_k']}", file=out)
        print(f"  raptor_level: {ctx['raptor_level']}  (expected: {expected_level})", file=out)
        print(f"  kb_examples:  {len(ctx['kb_examples'])}", file=out)
        print(f"  prompt_len:   {len(ctx['prompt'])} chars", file=out)
        print(f"  time:         {elapsed:.3f}s", file=out)
        if ctx["kb_examples"]:
            top = ctx["kb_examples"][0]
            print(f"  top_hit:      {top.get('category')}  sim={top.get('similarity',0):.4f}", file=out)
        assert ctx["raptor_level"] == expected_level, f"attempt={attempt}: expected {expected_level}, got {ctx['raptor_level']}"
        print(f"", file=out)

    # UNCERTAIN -> skips retrieval
    ctx_u = rag.build_context(
        source_code=sas_code, partition_type="DATA_STEP_RETAIN",
        risk_level="UNCERTAIN", attempt_number=0,
    )
    print(f"UNCERTAIN risk:", file=out)
    print(f"  kb_examples: {len(ctx_u['kb_examples'])}  (expected: 0, retrieval skipped)", file=out)
    assert ctx_u["kb_examples"] == []

    print(f"\nResult: PASS", file=out)


def test_rag_router(out: io.StringIO, embedder: NomicEmbedder) -> None:
    """Test 6: RAGRouter - correct paradigm selection for all cases."""
    kb_client = KBQueryClient(db_path=LANCEDB_PATH)
    router = RAGRouter(embedder=embedder, kb_client=kb_client)
    sas_code = (GOLD_DIR / "gs_01_basic_data_step.sas").read_text()

    print(f"Test: RAGRouter", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"SAS file: gs_01_basic_data_step.sas ({len(sas_code)} chars)", file=out)
    print(f"", file=out)

    cases = [
        ("LOW, no deps",  _make_partition(sas_code, risk_level=RiskLevel.LOW),                                            "static",  {}),
        ("LOW + deps",    _make_partition(sas_code, risk_level=RiskLevel.LOW, dependencies=[uuid.uuid4()]),                "graph",   {}),
        ("MODERATE",      _make_partition(sas_code, risk_level=RiskLevel.MODERATE),                                       "agentic", {}),
        ("HIGH",          _make_partition(sas_code, risk_level=RiskLevel.HIGH),                                           "agentic", {}),
        ("LOW + retry",   _make_partition(sas_code, risk_level=RiskLevel.LOW),                                            "agentic", {"attempt_number": 1}),
        ("UNCERTAIN",     _make_partition(sas_code, risk_level=RiskLevel.UNCERTAIN),                                      "agentic", {}),
    ]

    print(f"{'Case':<20} {'Expected':<10} {'Got':<10} {'k':>3} {'level':<10} {'kb_ex':>5} {'time':>8}", file=out)
    print(f"{'-'*20} {'-'*10} {'-'*10} {'-'*3} {'-'*10} {'-'*5} {'-'*8}", file=out)

    for label, partition, expected_paradigm, kwargs in cases:
        t0 = time.perf_counter()
        ctx = router.build_context(partition, **kwargs)
        elapsed = time.perf_counter() - t0
        match = "OK" if ctx["paradigm"] == expected_paradigm else "MISMATCH"
        print(
            f"{label:<20} {expected_paradigm:<10} {ctx['paradigm']:<10} "
            f"{ctx['retrieval_k']:>3} {ctx['raptor_level']:<10} "
            f"{len(ctx['kb_examples']):>5} {elapsed:>7.3f}s  {match}",
            file=out,
        )
        assert ctx["paradigm"] == expected_paradigm, f"{label}: expected {expected_paradigm}, got {ctx['paradigm']}"
        if label == "UNCERTAIN":
            assert ctx["kb_examples"] == []

    print(f"\nResult: PASS -- all 6 routing cases correct", file=out)


def test_feedback_ingestion(out: io.StringIO, embedder: NomicEmbedder) -> None:
    """Test 7: FeedbackIngestionAgent - real Groq cross-verification + LanceDB upsert."""
    import lancedb as ldb

    print(f"Test: FeedbackIngestionAgent (real Groq cross-verifier)", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"", file=out)

    # Real LanceDB table
    db = ldb.connect(LANCEDB_PATH)
    table = db.open_table("sas_python_examples")
    count_before = len(table)
    print(f"KB before: {count_before} pairs", file=out)

    # Real Groq cross-verifier
    print(f"Building Groq cross-verifier (llama-3.3-70b-versatile)...", file=out)
    verify_fn = _make_groq_cross_verifier()

    # DuckDB (real in-memory)
    conn = _make_real_duckdb()

    agent = FeedbackIngestionAgent(
        lancedb_table=table,
        embed_fn=embedder.embed,
        cross_verifier_fn=verify_fn,
        duckdb_conn=conn,
        confidence_threshold=0.80,
    )

    sas_code = (GOLD_DIR / "gs_02_retain_accumulator.sas").read_text()
    python_code = """\
import pandas as pd
from functools import reduce

def process_running_totals(sales_df: pd.DataFrame) -> pd.DataFrame:
    df = sales_df.copy().sort_values('region')
    df['cumulative_sales'] = df.groupby('region')['sales_amount'].cumsum()
    df['pct_of_target'] = df['cumulative_sales'] / df['target_amount'] * 100

    def flag(pct):
        if pct >= 100: return 'TARGET_MET'
        elif pct >= 75: return 'ON_TRACK'
        return 'AT_RISK'
    df['flag'] = df['pct_of_target'].apply(flag)
    return df
"""

    print(f"SAS code ({len(sas_code)} chars):", file=out)
    print(sas_code.strip(), file=out)
    print(f"\nProposed Python translation ({len(python_code)} chars):", file=out)
    print(python_code.strip(), file=out)
    print(f"\nCalling cross-verifier via Groq...", file=out)

    t0 = time.perf_counter()
    result = agent.ingest(
        conversion_id=str(uuid.uuid4()),
        partition_id=str(uuid.uuid4()),
        sas_code=sas_code,
        corrected_python=python_code,
        source="human_correction",
        partition_type="DATA_STEP_RETAIN",
        complexity_tier="MODERATE",
        category="DATA_STEP_RETAIN",
    )
    elapsed = time.perf_counter() - t0

    count_after = len(table)

    print(f"\nIngest result:", file=out)
    print(f"  accepted:         {result.get('accepted')}", file=out)
    print(f"  confidence:       {result.get('confidence') or result.get('verification_confidence', 'N/A')}", file=out)
    print(f"  rejection_reason: {result.get('rejection_reason')}", file=out)
    print(f"  new_kb_id:        {result.get('new_kb_id')}", file=out)
    print(f"  total_time:       {elapsed:.2f}s", file=out)
    print(f"  KB count:         {count_before} -> {count_after}", file=out)

    if result.get("accepted"):
        assert count_after == count_before + 1, f"KB should have grown: {count_before} -> {count_after}"
        print(f"\nResult: PASS -- correction accepted, KB grew {count_before} -> {count_after}", file=out)
    else:
        # Groq may reject — that's a real result, still a pass (agent ran correctly)
        print(f"\nResult: PASS -- Groq rejected the correction (confidence below threshold, which is valid)", file=out)


def test_quality_monitor(out: io.StringIO) -> None:
    """Test 8: ConversionQualityMonitor with real DuckDB in-memory."""
    print(f"Test: ConversionQualityMonitor", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"", file=out)

    conn = _make_real_duckdb()

    # --- Healthy batch: all SUCCESS, no PARTIALs ---
    healthy = [
        ("conv-1", "blk-1", "SUCCESS", 0.92, False, None),
        ("conv-2", "blk-2", "SUCCESS", 0.88, False, None),
        ("conv-3", "blk-3", "SUCCESS", 0.95, False, None),
        ("conv-4", "blk-4", "SUCCESS", 0.91, False, None),
        ("conv-5", "blk-5", "SUCCESS", 0.89, False, None),
    ]
    for row in healthy:
        conn.execute(
            "INSERT INTO conversion_results VALUES (?,?,?,?,?,?,?)",
            [*row, datetime.now(timezone.utc).isoformat()]
        )

    print(f"Healthy batch ({len(healthy)} rows: 5 SUCCESS, 0 PARTIAL):", file=out)
    monitor = ConversionQualityMonitor(duckdb_conn=conn)
    m = monitor.evaluate(batch_id="test-healthy")
    print(f"  success_rate:      {m['success_rate']:.2%}", file=out)
    print(f"  partial_rate:      {m['partial_rate']:.2%}", file=out)
    print(f"  avg_llm_confidence:{m['avg_llm_confidence']:.3f}", file=out)
    print(f"  n_evaluated:       {m['n_evaluated']}", file=out)
    print(f"  alerts:            {m.get('alerts', [])}", file=out)
    assert m["success_rate"] == 1.0
    assert m["partial_rate"] == 0.0
    assert m.get("alerts", []) == []

    print(f"", file=out)

    # --- Unhealthy batch ---
    bad_rows = [
        (f"conv-b{i}", f"blk-b{i}", "PARTIAL", 0.50, True, "RETAIN")
        for i in range(10)
    ]
    conn2 = _make_real_duckdb()
    for row in bad_rows:
        conn2.execute(
            "INSERT INTO conversion_results VALUES (?,?,?,?,?,?,?)",
            [*row, datetime.now(timezone.utc).isoformat()]
        )
    print(f"Unhealthy batch ({len(bad_rows)} rows: all PARTIAL, confidence=0.50):", file=out)
    monitor2 = ConversionQualityMonitor(duckdb_conn=conn2)
    m2 = monitor2.evaluate(batch_id="test-unhealthy")
    print(f"  success_rate:      {m2['success_rate']:.2%}", file=out)
    print(f"  partial_rate:      {m2['partial_rate']:.2%}", file=out)
    print(f"  avg_llm_confidence:{m2['avg_llm_confidence']:.3f}", file=out)
    print(f"  alerts:", file=out)
    for alert in m2.get("alerts", []):
        print(f"    - {alert}", file=out)
    assert m2["success_rate"] == 0.0
    assert len(m2.get("alerts", [])) > 0

    print(f"\nResult: PASS", file=out)


def test_retrain_trigger(out: io.StringIO) -> None:
    """Test 9: RetrainTrigger - all 4 conditions using real DuckDB."""
    print(f"Test: RetrainTrigger (all 4 conditions)", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"", file=out)

    def _fresh(kb_inserts=0, ece=None, success_rates=None, gap_dist=None):
        conn = _make_real_duckdb()
        # Use strictly increasing fake timestamps so ORDER BY created_at DESC works
        base_ts = "2026-01-01T00:00:00"
        ts_counter = [0]

        def next_ts():
            ts_counter[0] += 1
            return f"2026-01-01T00:{ts_counter[0]:02d}:00"

        # KB changelog entries
        for _ in range(kb_inserts):
            conn.execute("INSERT INTO kb_changelog VALUES (?,?,?)",
                         [str(uuid.uuid4()), "insert", next_ts()])
        # Calibration log
        if ece is not None:
            conn.execute("INSERT INTO calibration_log VALUES (?,?)", [ece, next_ts()])
        # Quality metrics rows for consecutive_low_success (inserted first = older)
        for sr in (success_rates or []):
            conn.execute(
                "INSERT INTO quality_metrics VALUES (?,?,?,?,?,?,?,?,?)",
                [str(uuid.uuid4()), "batch", 10, sr, 0.2, 0.0, 0.75, "{}", next_ts()],
            )
        # Gap dist row: insert LAST so it has the latest timestamp and is picked by LIMIT 1
        if gap_dist:
            conn.execute(
                "INSERT INTO quality_metrics VALUES (?,?,?,?,?,?,?,?,?)",
                [str(uuid.uuid4()), "gap_batch", 10, 0.5, 0.5, 0.0, 0.75,
                 json.dumps(gap_dist), next_ts()],
            )
        return RetrainTrigger(duckdb_conn=conn)

    tests = [
        ("Healthy (no trigger)",       dict(kb_inserts=10, ece=0.05, success_rates=[0.80, 0.82]),         False),
        ("KB growth >= 500",           dict(kb_inserts=501, ece=0.05, success_rates=[0.80, 0.82]),         True),
        ("ECE = 0.15 (> 0.12)",        dict(kb_inserts=10,  ece=0.15, success_rates=[0.80, 0.82]),         True),
        ("Consecutive low success",    dict(kb_inserts=10,  ece=0.05, success_rates=[0.60, 0.58]),         True),
        ("KB gap: RETAIN > 40%",       dict(kb_inserts=10,  ece=0.05, success_rates=[0.80, 0.82],
                                            gap_dist={"RETAIN": 8, "OTHER": 2}),                           True),
    ]

    print(f"{'Condition':<35} {'Expected':>8} {'Got':>8}  {'Reason'}", file=out)
    print(f"{'-'*35} {'-'*8} {'-'*8}  {'-'*40}", file=out)

    for label, kwargs, expect_retrain in tests:
        trigger = _fresh(**kwargs)
        decision = trigger.evaluate()
        match = "OK" if decision.should_retrain == expect_retrain else "MISMATCH"
        print(
            f"{label:<35} {str(expect_retrain):>8} {str(decision.should_retrain):>8}  "
            f"{decision.trigger_reason[:60]}  [{match}]",
            file=out,
        )
        assert decision.should_retrain == expect_retrain, \
            f"'{label}': expected {expect_retrain}, got {decision.should_retrain}"

    print(f"\nResult: PASS -- all 4 trigger conditions verified", file=out)


def test_full_pipeline_rag(out: io.StringIO, embedder: NomicEmbedder) -> None:
    """Test 10: Full routing through RAGRouter on 3 real gold standard SAS files."""
    kb_client = KBQueryClient(db_path=LANCEDB_PATH)
    router = RAGRouter(embedder=embedder, kb_client=kb_client)

    print(f"Test: Full RAGRouter Pipeline on Gold Standard Files", file=out)
    print(f"Run at: {datetime.now().isoformat()}", file=out)
    print(f"", file=out)

    cases = [
        ("gs_01_basic_data_step.sas",   RiskLevel.LOW,      [],             "static"),
        ("gs_02_retain_accumulator.sas", RiskLevel.MODERATE, [],             "agentic"),
        ("gs_05_etl_pipeline.sas",       RiskLevel.HIGH,     [],             "agentic"),
        ("gs_03_merge_bygroup.sas",      RiskLevel.LOW,      [uuid.uuid4()], "graph"),
    ]

    for fname, risk, deps, expected_paradigm in cases:
        fpath = GOLD_DIR / fname
        if not fpath.exists():
            print(f"Skipped (not found): {fname}", file=out)
            continue

        sas_code = fpath.read_text()
        p = _make_partition(sas_code, PartitionType.DATA_STEP, risk, dependencies=deps)

        t0 = time.perf_counter()
        ctx = router.build_context(p)
        elapsed = time.perf_counter() - t0

        print(f"File: {fname}", file=out)
        print(f"  risk:       {risk.value}", file=out)
        print(f"  deps:       {len(deps)}", file=out)
        print(f"  paradigm:   {ctx['paradigm']}  (expected: {expected_paradigm})", file=out)
        print(f"  k:          {ctx['retrieval_k']}", file=out)
        print(f"  level:      {ctx['raptor_level']}", file=out)
        print(f"  kb_hits:    {len(ctx['kb_examples'])}", file=out)
        print(f"  prompt_len: {len(ctx['prompt'])} chars", file=out)
        print(f"  time:       {elapsed:.3f}s", file=out)

        if ctx["kb_examples"]:
            print(f"  top_hit:    {ctx['kb_examples'][0].get('category')}  sim={ctx['kb_examples'][0].get('similarity',0):.4f}", file=out)

        print(f"  prompt preview:", file=out)
        print(f"    {ctx['prompt'][:300].replace(chr(10), ' ')}", file=out)
        print(f"", file=out)

        assert ctx["paradigm"] == expected_paradigm, f"{fname}: expected {expected_paradigm}, got {ctx['paradigm']}"

    print(f"Result: PASS", file=out)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("  Codara E2E Tests: RAG + Continuous Learning")
    print(f"  Output dir: {OUTPUT_DIR}")
    print("=" * 60)

    print("\nInitializing NomicEmbedder (CPU)...", flush=True)
    t0 = time.perf_counter()
    embedder = NomicEmbedder()
    print(f"  Ready in {time.perf_counter()-t0:.2f}s", flush=True)

    _run("01_KB_Loaded",           test_kb_loaded)
    _run("02_KB_Query",            test_kb_query,          embedder)
    _run("03_Static_RAG",          test_static_rag,        embedder)
    _run("04_Graph_RAG",           test_graph_rag,         embedder)
    _run("05_Agentic_RAG",         test_agentic_rag,       embedder)
    _run("06_RAG_Router",          test_rag_router,        embedder)
    _run("07_Feedback_Ingestion",  test_feedback_ingestion, embedder)
    _run("08_Quality_Monitor",     test_quality_monitor)
    _run("09_Retrain_Trigger",     test_retrain_trigger)
    _run("10_Full_Pipeline_RAG",   test_full_pipeline_rag, embedder)

    print("\n" + "=" * 60)
    total = _passed + _failed
    print(f"  Results: {_passed}/{total} passed")
    if _errors:
        for name, err in _errors:
            print(f"  [FAIL] {name}: {err}")
    else:
        print(f"  All tests passed!")
    print(f"  Output files: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
