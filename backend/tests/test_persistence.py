"""Tests for the Persistence & Index layer (week 7).

Covers:
    - PersistenceAgent  (#10) — SQLite write + dedup
    - IndexAgent        (#11) — DAG build, SCC detection, hop cap
    - NetworkXGraphBuilder    — persistent graph + multi-hop traversal
    - DuckDB manager          — all 7 analytics tables
    - ProjectConfigManager    — YAML hop cap persistence
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import networkx as nx
import pytest

from partition.index.index_agent import IndexAgent
from partition.index.graph_builder import NetworkXGraphBuilder
from partition.db.duckdb_manager import init_all_duckdb_tables
from partition.config.config_manager import ProjectConfigManager


# =====================================================================
# Helpers
# =====================================================================


def _mock_partition(
    content_hash: str = "test_hash",
    partition_id: str | None = None,
    file_id: str | None = None,
    raw_code: str = "DATA test; SET input; RUN;",
    dependency_refs: list | None = None,
    macro_scope: dict | None = None,
    variable_scope: dict | None = None,
):
    """Create a mock partition object for testing."""
    p = MagicMock()
    p.partition_id = partition_id or str(uuid.uuid4())
    p.block_id = p.partition_id
    p.source_file_id = file_id or str(uuid.uuid4())
    p.file_id = p.source_file_id
    p.file_path = f"/mock/{p.source_file_id}.sas"
    p.content_hash = content_hash
    p.partition_type.value = "DATA_STEP"
    p.partition_type.__str__ = lambda self: "DATA_STEP"
    p.risk_level.value = "LOW"
    p.risk_level.__str__ = lambda self: "LOW"
    p.conversion_status.value = "HUMAN_REVIEW"
    p.complexity_score = 0.2
    p.calibration_confidence = 0.8
    p.strategy.value = "FLAT_PARTITION"
    p.line_start = 1
    p.line_end = 10
    p.control_depth = 0
    p.has_macros = False
    p.has_nested_sql = False
    p.macro_scope = macro_scope or {}
    p.variable_scope = variable_scope or {}
    p.dependency_refs = dependency_refs or []
    p.raptor_leaf_id = "leaf-1"
    p.raptor_cluster_id = None
    p.raptor_root_id = None
    p.scc_id = None
    p.test_coverage_type = "full"
    p.raw_code = raw_code
    p.source_code = raw_code
    p.trace_id = uuid.uuid4()
    return p


# =====================================================================
# PersistenceAgent
# =====================================================================


class TestPersistenceAgent:
    """Test SQLite persistence + content-hash dedup."""

    def test_sql_write(self, tmp_path):
        """Write partitions to SQLite, verify count."""
        from partition.persistence.persistence_agent import PersistenceAgent

        db_path = tmp_path / "test.db"
        agent = PersistenceAgent(db_url=f"sqlite:///{db_path}")

        p1 = _mock_partition(raw_code="DATA a; RUN;")
        p2 = _mock_partition(raw_code="DATA b; RUN;")

        count = asyncio.run(agent.process([p1, p2]))
        assert count == 2

    def test_sql_dedup(self, tmp_path):
        """Second insert with same content_hash should be skipped."""
        from partition.persistence.persistence_agent import PersistenceAgent

        db_path = tmp_path / "test.db"
        agent = PersistenceAgent(db_url=f"sqlite:///{db_path}")

        p1 = _mock_partition(raw_code="DATA same; RUN;")
        p2 = _mock_partition(raw_code="DATA same; RUN;")  # identical content

        count1 = asyncio.run(agent.process([p1]))
        assert count1 == 1

        count2 = asyncio.run(agent.process([p2]))
        assert count2 == 0  # deduped

    def test_table_creation(self, tmp_path):
        """All required tables should be created on init."""
        from partition.persistence.persistence_agent import PersistenceAgent
        from sqlalchemy import inspect

        db_path = tmp_path / "test.db"
        agent = PersistenceAgent(db_url=f"sqlite:///{db_path}")
        inspector = inspect(agent.engine)
        tables = inspector.get_table_names()
        assert "partition_ir" in tables
        assert "file_registry" in tables
        assert "conversion_results" in tables
        assert "merged_scripts" in tables

    def test_empty_partitions(self, tmp_path):
        """Empty partition list returns 0."""
        from partition.persistence.persistence_agent import PersistenceAgent

        db_path = tmp_path / "test.db"
        agent = PersistenceAgent(db_url=f"sqlite:///{db_path}")
        count = asyncio.run(agent.process([]))
        assert count == 0

    def test_pipeline_twice_same_count(self, tmp_path):
        """Running pipeline twice should not double the row count."""
        from partition.persistence.persistence_agent import PersistenceAgent
        from sqlalchemy import text

        db_path = tmp_path / "test.db"
        agent = PersistenceAgent(db_url=f"sqlite:///{db_path}")

        partitions = [_mock_partition(raw_code=f"DATA x{i}; RUN;") for i in range(5)]

        count1 = asyncio.run(agent.process(partitions))
        count2 = asyncio.run(agent.process(partitions))
        assert count1 == 5
        assert count2 == 0  # all deduped

        with agent.engine.connect() as conn:
            total = conn.execute(text("SELECT COUNT(*) FROM partition_ir")).scalar()
        assert total == 5


# =====================================================================
# IndexAgent
# =====================================================================


class TestIndexAgent:
    """Test DAG build, SCC detection, hop cap."""

    def test_scc_detection(self):
        """Detect circular dependency A→B→C→A."""
        agent = IndexAgent()
        dag = nx.DiGraph()
        dag.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])
        sccs = agent._detect_scc(dag)
        assert len(sccs) == 1
        assert len(sccs[0]) == 3

    def test_no_scc_in_dag(self):
        """Acyclic graph → no SCCs."""
        agent = IndexAgent()
        dag = nx.DiGraph()
        dag.add_edges_from([("A", "B"), ("B", "C"), ("C", "D")])
        sccs = agent._detect_scc(dag)
        assert len(sccs) == 0

    def test_hop_cap(self):
        """Hop cap should equal longest path, capped at 10."""
        agent = IndexAgent()
        dag = nx.DiGraph()
        # range(5) → 5 edges: (0,1),(1,2),(2,3),(3,4),(4,5) → longest path = 5
        dag.add_edges_from([(str(i), str(i + 1)) for i in range(5)])
        hop = agent._compute_hop_cap(dag)
        assert hop == 5

    def test_hop_cap_max(self):
        """Chains > 10 should be capped."""
        agent = IndexAgent()
        dag = nx.DiGraph()
        dag.add_edges_from([(str(i), str(i + 1)) for i in range(15)])
        hop = agent._compute_hop_cap(dag)
        assert hop == 10

    def test_condense_removes_cycles(self):
        """Condensed graph must be acyclic."""
        agent = IndexAgent()
        dag = nx.DiGraph()
        dag.add_edges_from([("A", "B"), ("B", "C"), ("C", "A"), ("A", "D")])
        sccs = agent._detect_scc(dag)
        condensed = agent._condense(dag, sccs)
        assert nx.is_directed_acyclic_graph(condensed)

    def test_annotate_scc(self):
        """Partitions in an SCC should get scc_id set."""
        agent = IndexAgent()
        p_a = _mock_partition(partition_id="A")
        p_b = _mock_partition(partition_id="B")
        p_c = _mock_partition(partition_id="C")
        scc_groups = [{"A", "B"}]
        agent._annotate_scc([p_a, p_b, p_c], scc_groups)
        assert p_a.scc_id == "scc_0"
        assert p_b.scc_id == "scc_0"
        # p_c is NOT in the SCC — its scc_id should remain None (not modified)

    def test_build_dag_with_deps(self):
        """DAG should have edges for dataset dependencies."""
        agent = IndexAgent()
        fid = str(uuid.uuid4())
        p1 = _mock_partition(
            partition_id="p1", file_id=fid,
            variable_scope={"outputs": ["SALES"]},
        )
        p2 = _mock_partition(
            partition_id="p2", file_id=fid,
            dependency_refs=["SALES"],
        )
        dag = agent._build_dag([p1, p2], {})
        assert dag.has_edge("p2", "p1")

    def test_full_process(self):
        """Full process returns dag, sccs, condensed, hop_cap."""
        agent = IndexAgent()
        fid = str(uuid.uuid4())
        p1 = _mock_partition(partition_id="p1", file_id=fid)
        p2 = _mock_partition(partition_id="p2", file_id=fid)
        result = asyncio.run(agent.process([p1, p2]))
        assert "dag" in result
        assert "sccs" in result
        assert "condensed" in result
        assert "hop_cap" in result
        assert isinstance(result["hop_cap"], int)


# =====================================================================
# NetworkXGraphBuilder
# =====================================================================


class TestNetworkXGraphBuilder:
    """Test persistent graph builder with multi-hop traversal."""

    def test_add_partitions(self, tmp_path):
        """Adding partitions should increase node count."""
        builder = NetworkXGraphBuilder(
            persist_path=str(tmp_path / "test.gpickle")
        )
        partitions = [_mock_partition(partition_id=f"p{i}") for i in range(3)]
        added = builder.add_partitions(partitions)
        assert added == 3
        assert builder.count_nodes() == 3

    def test_add_edges(self, tmp_path):
        """Adding a DAG's edges should increase edge count."""
        builder = NetworkXGraphBuilder(
            persist_path=str(tmp_path / "test.gpickle")
        )
        partitions = [_mock_partition(partition_id=f"p{i}") for i in range(3)]
        builder.add_partitions(partitions)

        dag = nx.DiGraph()
        dag.add_edge("p0", "p1", dep_type="dataset", ref_raw="MY_TABLE")
        dag.add_edge("p1", "p2", dep_type="macro_call", macro_name="MY_MACRO")
        added = builder.add_edges(dag)
        assert added == 2
        assert builder.count_edges() == 2

    def test_multi_hop_traversal(self, tmp_path):
        """Multi-hop traversal should return transitive dependencies."""
        builder = NetworkXGraphBuilder(
            persist_path=str(tmp_path / "test.gpickle")
        )
        # Build A → B → C chain
        for nid in ["A", "B", "C"]:
            builder.graph.add_node(nid, partition_type="DATA_STEP", risk_level="LOW", scc_id="")
        builder.graph.add_edge("A", "B", edge_type="DEPENDS_ON")
        builder.graph.add_edge("B", "C", edge_type="DEPENDS_ON")
        builder.save()

        deps = builder.query_dependencies("A", max_hop=2)
        dep_ids = {d["partition_id"] for d in deps}
        assert "B" in dep_ids
        assert "C" in dep_ids

    def test_persistence(self, tmp_path):
        """Graph should survive save/load cycle."""
        path = str(tmp_path / "test.gpickle")
        builder1 = NetworkXGraphBuilder(persist_path=path)
        builder1.graph.add_node("X", partition_type="PROC_BLOCK", risk_level="HIGH", scc_id="")
        builder1.save()

        builder2 = NetworkXGraphBuilder(persist_path=path)
        assert builder2.count_nodes() == 1
        assert "X" in builder2.graph

    def test_scc_members_query(self, tmp_path):
        """query_scc_members should return all members of an SCC group."""
        builder = NetworkXGraphBuilder(
            persist_path=str(tmp_path / "test.gpickle")
        )
        builder.graph.add_node("A", scc_id="scc_0")
        builder.graph.add_node("B", scc_id="scc_0")
        builder.graph.add_node("C", scc_id="scc_1")
        builder.save()

        members = builder.query_scc_members("scc_0")
        assert set(members) == {"A", "B"}


# =====================================================================
# DuckDB manager
# =====================================================================


class TestDuckDB:
    """Test DuckDB analytics table creation."""

    def test_all_tables_created(self, tmp_path):
        """All 7 DuckDB analytics tables should be created."""
        import duckdb

        db_path = str(tmp_path / "test.duckdb")
        init_all_duckdb_tables(db_path)

        con = duckdb.connect(db_path)
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        expected = [
            "llm_audit",
            "calibration_log",
            "ablation_results",
            "quality_metrics",
            "feedback_log",
            "kb_changelog",
            "conversion_reports",
        ]
        for t in expected:
            assert t in tables, f"Missing table: {t}"
        con.close()

    def test_llm_audit_insert(self, tmp_path):
        """Inserting a row into llm_audit should succeed."""
        import duckdb
        from partition.db.duckdb_manager import log_llm_call

        db_path = str(tmp_path / "test.duckdb")
        init_all_duckdb_tables(db_path)
        log_llm_call(
            db_path,
            call_id="call-001",
            agent_name="TestAgent",
            model_name="llama-3.1-70b",
            prompt_hash="abc123",
            response_hash="def456",
            latency_ms=150.5,
            success=True,
        )
        con = duckdb.connect(db_path)
        count = con.execute("SELECT COUNT(*) FROM llm_audit").fetchone()[0]
        assert count == 1
        con.close()


# =====================================================================
# ProjectConfigManager
# =====================================================================


class TestProjectConfigManager:
    """Test YAML-based config manager."""

    def test_set_and_get_max_hop(self, tmp_path):
        """set_max_hop → get_max_hop should round-trip."""
        config_path = str(tmp_path / "config.yaml")
        mgr = ProjectConfigManager(config_path=config_path)
        mgr.set_max_hop(7)
        assert mgr.get_max_hop() == 7

    def test_default_hop(self, tmp_path):
        """Default hop cap should be 3."""
        config_path = str(tmp_path / "config.yaml")
        mgr = ProjectConfigManager(config_path=config_path)
        assert mgr.get_max_hop() == 3

    def test_persistence(self, tmp_path):
        """Config should survive reload."""
        config_path = str(tmp_path / "config.yaml")
        mgr1 = ProjectConfigManager(config_path=config_path)
        mgr1.set_max_hop(5)

        mgr2 = ProjectConfigManager(config_path=config_path)
        assert mgr2.get_max_hop() == 5

    def test_generic_set_get(self, tmp_path):
        """Generic set/get should work."""
        config_path = str(tmp_path / "config.yaml")
        mgr = ProjectConfigManager(config_path=config_path)
        mgr.set("pipeline_version", "0.7.0")
        assert mgr.get("pipeline_version") == "0.7.0"
