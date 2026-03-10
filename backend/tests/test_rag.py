"""Tests for the 3-tier RAG system (Static, GraphRAG, Agentic) and PromptManager.

Run with:
    cd sas_converter
    ../venv/Scripts/python -m pytest tests/test_rag.py -v
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from partition.models.enums import PartitionType, RiskLevel
from partition.models.partition_ir import PartitionIR
from partition.prompts import PromptManager
from partition.rag import RAGRouter, StaticRAG, GraphRAG, AgenticRAG


# ── Helpers ───────────────────────────────────────────────────────────────────

SAS_CODE = "data out; set inp; x = 1; run;"

_KB_EXAMPLES = [
    {
        "example_id": "ex1",
        "sas_code": "data a; set b; run;",
        "python_code": "a = b.copy()",
        "similarity": 0.85,
    },
    {
        "example_id": "ex2",
        "sas_code": "proc means; run;",
        "python_code": "df.describe()",
        "similarity": 0.72,
    },
]

_EMBEDDING = [0.1] * 768


def _make_partition(
    ptype: PartitionType = PartitionType.DATA_STEP,
    risk: RiskLevel = RiskLevel.LOW,
    scc_id: str | None = None,
    deps: list | None = None,
) -> PartitionIR:
    return PartitionIR(
        file_id=uuid4(),
        partition_type=ptype,
        source_code=SAS_CODE,
        line_start=1,
        line_end=5,
        risk_level=risk,
        dependencies=deps or [],
        metadata={
            "scc_id": scc_id,
            "complexity_confidence": 0.65,
        },
    )


def _mock_kb():
    kb = MagicMock()
    kb.retrieve_examples.return_value = list(_KB_EXAMPLES)
    return kb


def _mock_embedder():
    emb = MagicMock()
    emb.embed.return_value = list(_EMBEDDING)
    return emb


def _mock_graph():
    g = MagicMock()
    g.query_dependencies.return_value = [
        {"partition_id": "dep-1", "partition_type": "PROC_BLOCK"},
        {"partition_id": "dep-2", "partition_type": "MACRO_DEFINITION"},
    ]
    g.query_scc_members.return_value = ["scc-a", "scc-b", "scc-c"]
    g.graph = MagicMock()
    g.graph.nodes = MagicMock()
    g.graph.nodes.get = MagicMock(return_value={
        "partition_type": "DATA_STEP",
        "line_start": 10,
        "line_end": 20,
    })
    return g


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  PromptManager tests                                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestPromptManager:
    """Tests for template loading and rendering."""

    def test_list_templates_returns_all_six(self):
        pm = PromptManager()
        templates = pm.list_templates()
        expected = {
            "cross_verify",
            "entity_extraction",
            "reflection",
            "translation_agentic",
            "translation_graph",
            "translation_static",
        }
        assert expected == set(templates)

    def test_render_static_contains_sas_code(self):
        pm = PromptManager()
        result = pm.render(
            "translation_static",
            sas_code=SAS_CODE,
            partition_type="DATA_STEP",
            risk_level="LOW",
            target_label="Python (pandas)",
            complexity=0.42,
            failure_mode_rules="",
            kb_examples=[],
        )
        assert SAS_CODE in result
        assert "DATA_STEP" in result
        assert "Static RAG" in result

    def test_render_static_includes_kb_examples(self):
        pm = PromptManager()
        result = pm.render(
            "translation_static",
            sas_code=SAS_CODE,
            partition_type="DATA_STEP",
            risk_level="LOW",
            target_label="Python (pandas)",
            complexity=0.5,
            failure_mode_rules="",
            kb_examples=_KB_EXAMPLES,
        )
        assert "Reference Examples" in result
        assert "ex1" not in result  # example_id not rendered, but code is
        assert "a = b.copy()" in result

    def test_render_cross_verify_contains_both_codes(self):
        pm = PromptManager()
        result = pm.render(
            "cross_verify",
            sas_code="data x; run;",
            python_code="x = pd.DataFrame()",
            failure_mode=None,
        )
        assert "data x; run;" in result
        assert "x = pd.DataFrame()" in result
        assert "Evaluation Criteria" in result

    def test_render_reflection_contains_error(self):
        pm = PromptManager()
        result = pm.render(
            "reflection",
            sas_code=SAS_CODE,
            python_code="broken = code",
            error_description="SyntaxError: unexpected indent",
            failure_mode="DATE_EPOCH",
        )
        assert "SyntaxError: unexpected indent" in result
        assert "DATE_EPOCH" in result

    def test_render_missing_template_raises(self):
        pm = PromptManager()
        with pytest.raises(Exception):
            pm.render("nonexistent_template", foo="bar")

    def test_custom_templates_dir(self, tmp_path):
        tpl = tmp_path / "hello.j2"
        tpl.write_text("Hello {{ name }}!")
        pm = PromptManager(templates_dir=tmp_path)
        assert pm.render("hello", name="World") == "Hello World!"


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RAGRouter.select_paradigm tests                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestRAGRouterSelect:
    """Test paradigm selection logic."""

    def _router(self):
        return RAGRouter(
            kb_client=_mock_kb(),
            embedder=_mock_embedder(),
            graph_builder=_mock_graph(),
            prompt_manager=PromptManager(),
        )

    # ── Agentic triggers ──────────────────────────────────────────────────

    def test_moderate_risk_selects_agentic(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.MODERATE)
        assert r.select_paradigm(p) == "agentic"

    def test_high_risk_selects_agentic(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.HIGH)
        assert r.select_paradigm(p) == "agentic"

    def test_uncertain_risk_selects_agentic(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.UNCERTAIN)
        assert r.select_paradigm(p) == "agentic"

    def test_failure_mode_selects_agentic(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW)
        assert r.select_paradigm(p, failure_mode="DATE_EPOCH") == "agentic"

    def test_retry_selects_agentic(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW)
        assert r.select_paradigm(p, attempt_number=1) == "agentic"

    # ── GraphRAG triggers ─────────────────────────────────────────────────

    def test_scc_membership_selects_graph(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW, scc_id="group-42")
        assert r.select_paradigm(p) == "graph"

    def test_dependencies_select_graph(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW, deps=[uuid4()])
        assert r.select_paradigm(p) == "graph"

    # ── Static fallback ───────────────────────────────────────────────────

    def test_low_no_deps_selects_static(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW)
        assert r.select_paradigm(p) == "static"

    # ── Priority: agentic > graph > static ────────────────────────────────

    def test_high_risk_with_deps_still_agentic(self):
        """Agentic takes priority over GraphRAG when risk is high."""
        r = self._router()
        p = _make_partition(risk=RiskLevel.HIGH, scc_id="g1", deps=[uuid4()])
        assert r.select_paradigm(p) == "agentic"


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  StaticRAG tests                                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestStaticRAG:
    """Tests for StaticRAG.build_context."""

    def _build(self, **overrides):
        defaults = dict(
            source_code=SAS_CODE,
            partition_type="DATA_STEP",
            risk_level="LOW",
            target_runtime="python",
            failure_mode=None,
            failure_mode_rules="",
            complexity=0.5,
        )
        defaults.update(overrides)
        rag = StaticRAG(
            kb_client=_mock_kb(),
            embedder=_mock_embedder(),
            prompt_manager=PromptManager(),
        )
        return rag.build_context(**defaults)

    def test_returns_required_keys(self):
        ctx = self._build()
        assert set(ctx.keys()) == {
            "prompt", "kb_examples", "paradigm", "retrieval_k", "raptor_level",
        }

    def test_paradigm_is_static(self):
        ctx = self._build()
        assert ctx["paradigm"] == "static"

    def test_retrieval_k_is_3(self):
        ctx = self._build()
        assert ctx["retrieval_k"] == 3

    def test_raptor_level_is_leaf(self):
        ctx = self._build()
        assert ctx["raptor_level"] == "leaf"

    def test_prompt_contains_sas_code(self):
        ctx = self._build()
        assert SAS_CODE in ctx["prompt"]

    def test_kb_examples_passed_through(self):
        ctx = self._build()
        assert len(ctx["kb_examples"]) == 2
        assert ctx["kb_examples"][0]["example_id"] == "ex1"

    def test_embedder_called_with_source(self):
        emb = _mock_embedder()
        rag = StaticRAG(
            kb_client=_mock_kb(), embedder=emb, prompt_manager=PromptManager(),
        )
        rag.build_context(
            source_code=SAS_CODE, partition_type="DATA_STEP",
            risk_level="LOW",
        )
        emb.embed.assert_called_once_with(SAS_CODE)

    def test_pyspark_runtime_label(self):
        ctx = self._build(target_runtime="pyspark")
        assert "PySpark" in ctx["prompt"]


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  GraphRAG tests                                                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestGraphRAG:
    """Tests for GraphRAG.build_context."""

    def _build(self, **overrides):
        defaults = dict(
            source_code=SAS_CODE,
            partition_type="DATA_STEP",
            risk_level="LOW",
            partition_id="part-1",
            target_runtime="python",
            failure_mode=None,
            failure_mode_rules="",
            complexity=0.5,
            scc_id="scc-group-7",
            translations={"dep-1": "import pandas as pd"},
            hop_cap=3,
        )
        defaults.update(overrides)
        rag = GraphRAG(
            kb_client=_mock_kb(),
            embedder=_mock_embedder(),
            graph_builder=_mock_graph(),
            prompt_manager=PromptManager(),
        )
        return rag.build_context(**defaults)

    def test_returns_required_keys(self):
        ctx = self._build()
        assert set(ctx.keys()) == {
            "prompt", "kb_examples", "graph_context", "scc_siblings",
            "paradigm", "retrieval_k", "raptor_level",
        }

    def test_paradigm_is_graph(self):
        ctx = self._build()
        assert ctx["paradigm"] == "graph"

    def test_retrieval_k_is_5(self):
        ctx = self._build()
        assert ctx["retrieval_k"] == 5

    def test_raptor_level_is_cluster(self):
        ctx = self._build()
        assert ctx["raptor_level"] == "cluster"

    def test_graph_context_populated(self):
        ctx = self._build()
        assert len(ctx["graph_context"]) == 2
        assert ctx["graph_context"][0]["partition_id"] == "dep-1"

    def test_upstream_translation_injected(self):
        ctx = self._build()
        dep1 = ctx["graph_context"][0]
        assert dep1["python_code"] == "import pandas as pd"

    def test_scc_siblings_excludes_self(self):
        ctx = self._build()
        sibling_ids = [s["partition_id"] for s in ctx["scc_siblings"]]
        assert "part-1" not in sibling_ids

    def test_empty_scc_id_no_siblings(self):
        ctx = self._build(scc_id="")
        assert ctx["scc_siblings"] == []

    def test_prompt_contains_graph_keyword(self):
        ctx = self._build()
        assert "Graph" in ctx["prompt"] or "graph" in ctx["prompt"]


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  AgenticRAG tests                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestAgenticRAG:
    """Tests for AgenticRAG.build_context."""

    def _make_rag(self):
        return AgenticRAG(
            kb_client=_mock_kb(),
            embedder=_mock_embedder(),
            graph_builder=_mock_graph(),
            prompt_manager=PromptManager(),
        )

    def _build(self, **overrides):
        defaults = dict(
            source_code=SAS_CODE,
            partition_type="DATA_STEP",
            risk_level="HIGH",
            partition_id="part-1",
            target_runtime="python",
            failure_mode=None,
            failure_mode_rules="",
            complexity=0.5,
            attempt_number=0,
            previous_issues=None,
            reflection="",
            error_description="",
            translations=None,
        )
        defaults.update(overrides)
        return self._make_rag().build_context(**defaults)

    def test_returns_required_keys(self):
        ctx = self._build()
        assert set(ctx.keys()) == {
            "prompt", "kb_examples", "graph_context",
            "paradigm", "retrieval_k", "raptor_level", "attempt_number",
        }

    def test_paradigm_is_agentic(self):
        ctx = self._build()
        assert ctx["paradigm"] == "agentic"

    # ── Adaptive k ────────────────────────────────────────────────────────

    def test_high_risk_k_is_8(self):
        ctx = self._build(risk_level="HIGH", attempt_number=0)
        assert ctx["retrieval_k"] == 8

    def test_moderate_risk_k_is_5(self):
        ctx = self._build(risk_level="MODERATE", attempt_number=0)
        assert ctx["retrieval_k"] == 5

    def test_k_escalates_on_retry(self):
        ctx0 = self._build(risk_level="MODERATE", attempt_number=0)
        ctx1 = self._build(risk_level="MODERATE", attempt_number=1)
        assert ctx1["retrieval_k"] == ctx0["retrieval_k"] + 3

    # ── RAPTOR level escalation ───────────────────────────────────────────

    def test_attempt_0_level_leaf(self):
        ctx = self._build(attempt_number=0)
        assert ctx["raptor_level"] == "leaf"

    def test_attempt_1_level_cluster(self):
        ctx = self._build(attempt_number=1)
        assert ctx["raptor_level"] == "cluster"

    def test_attempt_2_level_root(self):
        ctx = self._build(attempt_number=2)
        assert ctx["raptor_level"] == "root"

    def test_attempt_beyond_2_caps_at_root(self):
        ctx = self._build(attempt_number=5)
        assert ctx["raptor_level"] == "root"

    # ── UNCERTAIN skip ────────────────────────────────────────────────────

    def test_uncertain_skips_retrieval(self):
        ctx = self._build(risk_level="UNCERTAIN")
        assert ctx["kb_examples"] == []
        assert ctx["retrieval_k"] == 0
        assert ctx["raptor_level"] == "none"

    # ── Query reformulation ───────────────────────────────────────────────

    def test_retry_reformulates_query(self):
        emb = _mock_embedder()
        rag = AgenticRAG(
            kb_client=_mock_kb(), embedder=emb,
            graph_builder=_mock_graph(), prompt_manager=PromptManager(),
        )
        rag.build_context(
            source_code=SAS_CODE, partition_type="DATA_STEP",
            risk_level="HIGH", attempt_number=1,
            error_description="missing import numpy",
        )
        query_arg = emb.embed.call_args[0][0]
        assert "FAILURE_MODE" not in query_arg  # no failure_mode passed
        assert "missing import numpy" in query_arg

    def test_reformulation_includes_failure_mode(self):
        emb = _mock_embedder()
        rag = AgenticRAG(
            kb_client=_mock_kb(), embedder=emb,
            graph_builder=_mock_graph(), prompt_manager=PromptManager(),
        )
        rag.build_context(
            source_code=SAS_CODE, partition_type="DATA_STEP",
            risk_level="HIGH", attempt_number=1,
            failure_mode="MERGE_MANY_TO_MANY",
            error_description="wrong join",
        )
        query_arg = emb.embed.call_args[0][0]
        assert "FAILURE_MODE: MERGE_MANY_TO_MANY" in query_arg

    # ── Graph escalation on attempt ≥ 2 ──────────────────────────────────

    def test_graph_context_empty_on_attempt_0(self):
        ctx = self._build(attempt_number=0)
        assert ctx["graph_context"] == []

    def test_graph_context_populated_on_attempt_2(self):
        ctx = self._build(attempt_number=2, partition_id="part-1")
        assert len(ctx["graph_context"]) == 2


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RAGRouter.build_context integration tests                               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestRAGRouterBuildContext:
    """Integration tests: Router → paradigm → context dict."""

    def _router(self):
        return RAGRouter(
            kb_client=_mock_kb(),
            embedder=_mock_embedder(),
            graph_builder=_mock_graph(),
            prompt_manager=PromptManager(),
        )

    def test_static_route_returns_static_paradigm(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW)
        ctx = r.build_context(partition=p)
        assert ctx["paradigm"] == "static"
        assert "prompt" in ctx

    def test_graph_route_returns_graph_paradigm(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW, deps=[uuid4()])
        ctx = r.build_context(partition=p)
        assert ctx["paradigm"] == "graph"
        assert "graph_context" in ctx

    def test_agentic_route_returns_agentic_paradigm(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.HIGH)
        ctx = r.build_context(partition=p)
        assert ctx["paradigm"] == "agentic"
        assert "attempt_number" in ctx

    def test_retry_forces_agentic_even_for_low_risk(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW)
        ctx = r.build_context(partition=p, attempt_number=1)
        assert ctx["paradigm"] == "agentic"

    def test_failure_mode_routes_to_agentic(self):
        r = self._router()
        p = _make_partition(risk=RiskLevel.LOW)
        ctx = r.build_context(partition=p, failure_mode="DATE_EPOCH")
        assert ctx["paradigm"] == "agentic"

    def test_context_always_has_prompt_and_kb_examples(self):
        r = self._router()
        for risk in RiskLevel:
            p = _make_partition(risk=risk)
            ctx = r.build_context(partition=p)
            assert "prompt" in ctx
            assert "kb_examples" in ctx
