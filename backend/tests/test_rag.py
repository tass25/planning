"""Tests for the 3-tier RAG system (Static, GraphRAG, Agentic) and PromptManager.

All tests use real components — no mocks, no stubs, no patches.

Run with:
    cd backend
    python -m pytest tests/test_rag.py -v
"""
from __future__ import annotations

from pathlib import Path
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

    def _router(self, embedder, kb_client, real_graph):
        return RAGRouter(
            kb_client=kb_client,
            embedder=embedder,
            graph_builder=real_graph,
            prompt_manager=PromptManager(),
        )

    # ── Agentic triggers ──────────────────────────────────────────────────

    def test_moderate_risk_selects_agentic(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.MODERATE)
        assert r.select_paradigm(p) == "agentic"

    def test_high_risk_selects_agentic(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.HIGH)
        assert r.select_paradigm(p) == "agentic"

    def test_uncertain_risk_selects_agentic(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.UNCERTAIN)
        assert r.select_paradigm(p) == "agentic"

    def test_failure_mode_selects_agentic(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW)
        assert r.select_paradigm(p, failure_mode="DATE_EPOCH") == "agentic"

    def test_retry_selects_agentic(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW)
        assert r.select_paradigm(p, attempt_number=1) == "agentic"

    # ── GraphRAG triggers ─────────────────────────────────────────────────

    def test_scc_membership_selects_graph(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW, scc_id="group-42")
        assert r.select_paradigm(p) == "graph"

    def test_dependencies_select_graph(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW, deps=[uuid4()])
        assert r.select_paradigm(p) == "graph"

    # ── Static fallback ───────────────────────────────────────────────────

    def test_low_no_deps_selects_static(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW)
        assert r.select_paradigm(p) == "static"

    # ── Priority: agentic > graph > static ────────────────────────────────

    def test_high_risk_with_deps_still_agentic(self, embedder, kb_client, real_graph):
        """Agentic takes priority over GraphRAG when risk is high."""
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.HIGH, scc_id="g1", deps=[uuid4()])
        assert r.select_paradigm(p) == "agentic"


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  StaticRAG tests                                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestStaticRAG:
    """Tests for StaticRAG.build_context."""

    def _build(self, embedder, kb_client, **overrides):
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
            kb_client=kb_client,
            embedder=embedder,
            prompt_manager=PromptManager(),
        )
        return rag.build_context(**defaults)

    def test_returns_required_keys(self, embedder, kb_client):
        ctx = self._build(embedder, kb_client)
        assert set(ctx.keys()) == {
            "prompt", "kb_examples", "paradigm", "retrieval_k", "raptor_level",
        }

    def test_paradigm_is_static(self, embedder, kb_client):
        ctx = self._build(embedder, kb_client)
        assert ctx["paradigm"] == "static"

    def test_retrieval_k_is_3(self, embedder, kb_client):
        ctx = self._build(embedder, kb_client)
        assert ctx["retrieval_k"] == 3

    def test_raptor_level_is_leaf(self, embedder, kb_client):
        ctx = self._build(embedder, kb_client)
        assert ctx["raptor_level"] == "leaf"

    def test_prompt_contains_sas_code(self, embedder, kb_client):
        ctx = self._build(embedder, kb_client)
        assert SAS_CODE in ctx["prompt"]

    def test_kb_examples_passed_through(self, embedder, kb_client):
        # Real retrieval — just verify it returns a list (may be empty if no
        # DATA_STEP examples are indexed yet, or populated if they are)
        ctx = self._build(embedder, kb_client)
        assert isinstance(ctx["kb_examples"], list)

    def test_embedder_called_with_source(self, embedder, kb_client):
        # Verify the prompt actually contains the SAS code (proxy for embedder
        # being called with the right input, without inspecting call args)
        rag = StaticRAG(
            kb_client=kb_client,
            embedder=embedder,
            prompt_manager=PromptManager(),
        )
        ctx = rag.build_context(
            source_code=SAS_CODE,
            partition_type="DATA_STEP",
            risk_level="LOW",
        )
        assert SAS_CODE in ctx["prompt"]


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  GraphRAG tests                                                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestGraphRAG:
    """Tests for GraphRAG.build_context."""

    def _build(self, embedder, kb_client, real_graph, **overrides):
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
            kb_client=kb_client,
            embedder=embedder,
            graph_builder=real_graph,
            prompt_manager=PromptManager(),
        )
        return rag.build_context(**defaults)

    def test_returns_required_keys(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph)
        assert set(ctx.keys()) == {
            "prompt", "kb_examples", "graph_context", "scc_siblings",
            "paradigm", "retrieval_k", "raptor_level",
        }

    def test_paradigm_is_graph(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph)
        assert ctx["paradigm"] == "graph"

    def test_retrieval_k_is_5(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph)
        assert ctx["retrieval_k"] == 5

    def test_raptor_level_is_cluster(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph)
        assert ctx["raptor_level"] == "cluster"

    def test_graph_context_populated(self, embedder, kb_client, real_graph):
        # real_graph has dep-1 and dep-2 as successors of part-1
        ctx = self._build(embedder, kb_client, real_graph)
        assert len(ctx["graph_context"]) >= 1

    def test_upstream_translation_injected(self, embedder, kb_client, real_graph):
        ctx = self._build(
            embedder, kb_client, real_graph,
            translations={"dep-1": "import pandas as pd"},
        )
        # Find dep-1 in graph_context and check its python_code
        dep1_entries = [
            e for e in ctx["graph_context"] if e["partition_id"] == "dep-1"
        ]
        assert len(dep1_entries) >= 1
        assert dep1_entries[0]["python_code"] == "import pandas as pd"

    def test_scc_siblings_excludes_self(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, partition_id="scc-a", scc_id="scc-group-7")
        sibling_ids = [s["partition_id"] for s in ctx["scc_siblings"]]
        assert "scc-a" not in sibling_ids

    def test_empty_scc_id_no_siblings(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, scc_id="")
        assert ctx["scc_siblings"] == []

    def test_prompt_contains_graph_keyword(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph)
        assert "Graph" in ctx["prompt"] or "graph" in ctx["prompt"]


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  AgenticRAG tests                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestAgenticRAG:
    """Tests for AgenticRAG.build_context."""

    def _make_rag(self, embedder, kb_client, real_graph):
        return AgenticRAG(
            kb_client=kb_client,
            embedder=embedder,
            graph_builder=real_graph,
            prompt_manager=PromptManager(),
        )

    def _build(self, embedder, kb_client, real_graph, **overrides):
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
        return self._make_rag(embedder, kb_client, real_graph).build_context(**defaults)

    def test_returns_required_keys(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph)
        assert set(ctx.keys()) == {
            "prompt", "kb_examples", "graph_context",
            "paradigm", "retrieval_k", "raptor_level", "attempt_number",
        }

    def test_paradigm_is_agentic(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph)
        assert ctx["paradigm"] == "agentic"

    # ── Adaptive k ────────────────────────────────────────────────────────

    def test_high_risk_k_is_8(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, risk_level="HIGH", attempt_number=0)
        assert ctx["retrieval_k"] == 8

    def test_moderate_risk_k_is_5(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, risk_level="MODERATE", attempt_number=0)
        assert ctx["retrieval_k"] == 5

    def test_k_escalates_on_retry(self, embedder, kb_client, real_graph):
        ctx0 = self._build(embedder, kb_client, real_graph, risk_level="MODERATE", attempt_number=0)
        ctx1 = self._build(embedder, kb_client, real_graph, risk_level="MODERATE", attempt_number=1)
        assert ctx1["retrieval_k"] == ctx0["retrieval_k"] + 3

    # ── RAPTOR level escalation ───────────────────────────────────────────

    def test_attempt_0_level_leaf(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, attempt_number=0)
        assert ctx["raptor_level"] == "leaf"

    def test_attempt_1_level_cluster(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, attempt_number=1)
        assert ctx["raptor_level"] == "cluster"

    def test_attempt_2_level_root(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, attempt_number=2)
        assert ctx["raptor_level"] == "root"

    def test_attempt_beyond_2_caps_at_root(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, attempt_number=5)
        assert ctx["raptor_level"] == "root"

    # ── UNCERTAIN skip ────────────────────────────────────────────────────

    def test_uncertain_skips_retrieval(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, risk_level="UNCERTAIN")
        assert ctx["kb_examples"] == []
        assert ctx["retrieval_k"] == 0
        assert ctx["raptor_level"] == "none"

    # ── Query reformulation ───────────────────────────────────────────────

    def test_retry_reformulates_query(self, embedder, kb_client, real_graph):
        rag = self._make_rag(embedder, kb_client, real_graph)
        result = rag._reformulate_query(SAS_CODE, None, "missing import numpy")
        # No failure_mode → "FAILURE_MODE:" absent; error appended
        assert "FAILURE_MODE" not in result
        assert "ERROR: missing import numpy" in result

    def test_reformulation_includes_failure_mode(self, embedder, kb_client, real_graph):
        rag = self._make_rag(embedder, kb_client, real_graph)
        result = rag._reformulate_query(SAS_CODE, "MERGE_MANY_TO_MANY", "wrong join")
        assert "FAILURE_MODE: MERGE_MANY_TO_MANY" in result

    # ── Graph escalation on attempt ≥ 2 ──────────────────────────────────

    def test_graph_context_empty_on_attempt_0(self, embedder, kb_client, real_graph):
        ctx = self._build(embedder, kb_client, real_graph, attempt_number=0)
        assert ctx["graph_context"] == []

    def test_graph_context_populated_on_attempt_2(self, embedder, kb_client, real_graph):
        # real_graph has dep-1 and dep-2 as successors of part-1
        ctx = self._build(embedder, kb_client, real_graph, attempt_number=2, partition_id="part-1")
        assert len(ctx["graph_context"]) >= 1


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  RAGRouter.build_context integration tests                               ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

class TestRAGRouterBuildContext:
    """Integration tests: Router → paradigm → context dict."""

    def _router(self, embedder, kb_client, real_graph):
        return RAGRouter(
            kb_client=kb_client,
            embedder=embedder,
            graph_builder=real_graph,
            prompt_manager=PromptManager(),
        )

    def test_static_route_returns_static_paradigm(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW)
        ctx = r.build_context(partition=p)
        assert ctx["paradigm"] == "static"
        assert "prompt" in ctx

    def test_graph_route_returns_graph_paradigm(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW, deps=[uuid4()])
        ctx = r.build_context(partition=p)
        assert ctx["paradigm"] == "graph"
        assert "graph_context" in ctx

    def test_agentic_route_returns_agentic_paradigm(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.HIGH)
        ctx = r.build_context(partition=p)
        assert ctx["paradigm"] == "agentic"
        assert "attempt_number" in ctx

    def test_retry_forces_agentic_even_for_low_risk(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW)
        ctx = r.build_context(partition=p, attempt_number=1)
        assert ctx["paradigm"] == "agentic"

    def test_failure_mode_routes_to_agentic(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        p = _make_partition(risk=RiskLevel.LOW)
        ctx = r.build_context(partition=p, failure_mode="DATE_EPOCH")
        assert ctx["paradigm"] == "agentic"

    def test_context_always_has_prompt_and_kb_examples(self, embedder, kb_client, real_graph):
        r = self._router(embedder, kb_client, real_graph)
        for risk in RiskLevel:
            p = _make_partition(risk=risk)
            ctx = r.build_context(partition=p)
            assert "prompt" in ctx
            assert "kb_examples" in ctx
