"""RAGRouter — selects Static / GraphRAG / Agentic per partition.

Selection criteria (from cahier des charges §3.2):
  - **Static RAG** — LOW risk, no cross-file deps, no SCC membership
  - **GraphRAG**   — partition has cross-file dependencies or SCC membership
  - **Agentic RAG** — MOD/HIGH risk, or failure mode detected, or retry after
                       cross-verification failure

The router is stateless — it inspects partition metadata and delegates
to the appropriate paradigm's ``build_context()`` method.
"""

from __future__ import annotations

from typing import Optional

import structlog

from partition.models.partition_ir import PartitionIR
from partition.prompts import PromptManager
from partition.translation.kb_query import KBQueryClient
from partition.raptor.embedder import NomicEmbedder
from partition.index.graph_builder import NetworkXGraphBuilder

from .static_rag import StaticRAG
from .graph_rag import GraphRAG
from .agentic_rag import AgenticRAG

logger = structlog.get_logger()

# Partition types that are "simple" enough for Static RAG when LOW risk
_SIMPLE_TYPES = {"DATA_STEP", "PROC_BLOCK", "GLOBAL_STATEMENT", "INCLUDE_REFERENCE"}


class RAGRouter:
    """Three-tier RAG paradigm router.

    Instantiate once per pipeline run; shares KB client, embedder,
    and graph builder across all three paradigms for efficiency.
    """

    def __init__(
        self,
        kb_client: KBQueryClient | None = None,
        embedder: NomicEmbedder | None = None,
        graph_builder: NetworkXGraphBuilder | None = None,
        prompt_manager: PromptManager | None = None,
    ):
        kb = kb_client or KBQueryClient()
        emb = embedder or NomicEmbedder()
        graph = graph_builder or NetworkXGraphBuilder()
        pm = prompt_manager or PromptManager()

        self.static = StaticRAG(kb_client=kb, embedder=emb, prompt_manager=pm)
        self.graph = GraphRAG(kb_client=kb, embedder=emb, graph_builder=graph, prompt_manager=pm)
        self.agentic = AgenticRAG(kb_client=kb, embedder=emb, graph_builder=graph, prompt_manager=pm)

    def select_paradigm(
        self,
        partition: PartitionIR,
        attempt_number: int = 0,
        failure_mode: Optional[str] = None,
    ) -> str:
        """Determine which RAG paradigm to use.

        Returns one of: "static", "graph", "agentic".
        """
        risk = partition.risk_level.value
        has_scc = bool(partition.metadata.get("scc_id"))
        has_deps = len(partition.dependencies) > 0
        ptype = partition.partition_type.value

        # Agentic RAG: MOD/HIGH risk, failure mode, or retry
        if risk in ("MODERATE", "HIGH", "UNCERTAIN"):
            return "agentic"
        if failure_mode:
            return "agentic"
        if attempt_number > 0:
            return "agentic"

        # GraphRAG: cross-file deps or SCC membership
        if has_scc or has_deps:
            return "graph"

        # Static RAG: LOW risk, simple type, no deps
        return "static"

    def build_context(
        self,
        partition: PartitionIR,
        target_runtime: str = "python",
        failure_mode: Optional[str] = None,
        failure_mode_rules: str = "",
        attempt_number: int = 0,
        previous_issues: list[str] | None = None,
        reflection: str = "",
        error_description: str = "",
        translations: dict[str, str] | None = None,
        hop_cap: int = 3,
    ) -> dict:
        """Route to the selected paradigm and build the translation context.

        Returns the paradigm's context dict (prompt, kb_examples, paradigm, ...).
        """
        paradigm = self.select_paradigm(partition, attempt_number, failure_mode)
        pid = str(partition.block_id)
        complexity = partition.metadata.get("complexity_confidence", 0.5)
        scc_id = partition.metadata.get("scc_id", "")

        common = dict(
            source_code=partition.source_code,
            partition_type=partition.partition_type.value,
            risk_level=partition.risk_level.value,
            target_runtime=target_runtime,
            failure_mode=failure_mode,
            failure_mode_rules=failure_mode_rules,
            complexity=complexity,
            z3_repair_hint=partition.metadata.get("z3_repair_hint", ""),
        )

        if paradigm == "static":
            ctx = self.static.build_context(**common)

        elif paradigm == "graph":
            ctx = self.graph.build_context(
                **common,
                partition_id=pid,
                scc_id=scc_id,
                translations=translations,
                hop_cap=hop_cap,
            )

        else:  # agentic
            ctx = self.agentic.build_context(
                **common,
                partition_id=pid,
                attempt_number=attempt_number,
                previous_issues=previous_issues,
                reflection=reflection,
                error_description=error_description,
                translations=translations,
            )

        logger.info(
            "rag_paradigm_selected",
            paradigm=paradigm,
            partition_type=partition.partition_type.value,
            risk_level=partition.risk_level.value,
            attempt=attempt_number,
        )
        return ctx
