"""GraphRAG — dependency-aware retrieval with graph context injection.

Before querying the KB, traverses the NetworkX dependency graph to
collect structural context: upstream translations, downstream consumers,
and SCC siblings.  Graph context is injected alongside KB pairs.
Retrieves at RAPTOR cluster level (k=5) for macro-family awareness.
"""

from __future__ import annotations

from typing import Optional

import structlog

from partition.prompts import PromptManager
from partition.translation.kb_query import KBQueryClient
from partition.raptor.embedder import NomicEmbedder
from partition.index.graph_builder import NetworkXGraphBuilder

logger = structlog.get_logger()


class GraphRAG:
    """GraphRAG paradigm — graph-traversal + cluster-level KB retrieval.

    Used when a partition has cross-file dependencies, is part of an
    SCC group, or uses macros defined in other files.
    """

    K = 5
    PARADIGM_NAME = "graph"

    def __init__(
        self,
        kb_client: KBQueryClient | None = None,
        embedder: NomicEmbedder | None = None,
        graph_builder: NetworkXGraphBuilder | None = None,
        prompt_manager: PromptManager | None = None,
    ):
        self.kb = kb_client or KBQueryClient()
        self.embedder = embedder or NomicEmbedder()
        self.graph = graph_builder or NetworkXGraphBuilder()
        self.pm = prompt_manager or PromptManager()

    def _get_graph_context(
        self,
        partition_id: str,
        max_hop: int = 3,
        translations: dict[str, str] | None = None,
    ) -> list[dict]:
        """Traverse dependency graph and collect upstream/downstream context."""
        deps = self.graph.query_dependencies(partition_id, max_hop=max_hop)
        translations = translations or {}

        context = []
        for dep in deps:
            pid = dep["partition_id"]
            context.append({
                "partition_id": pid,
                "partition_type": dep.get("partition_type", ""),
                "relation": "upstream",
                "python_code": translations.get(pid, ""),
            })
        return context

    def _get_scc_siblings(
        self,
        scc_id: str,
        current_partition_id: str,
    ) -> list[dict]:
        """Get all partitions in the same SCC (excluding current)."""
        if not scc_id:
            return []
        members = self.graph.query_scc_members(scc_id)
        siblings = []
        for pid in members:
            if pid == current_partition_id:
                continue
            node_data = self.graph.graph.nodes.get(pid, {})
            siblings.append({
                "partition_id": pid,
                "partition_type": node_data.get("partition_type", ""),
                "line_start": node_data.get("line_start", "?"),
                "line_end": node_data.get("line_end", "?"),
            })
        return siblings

    def build_context(
        self,
        source_code: str,
        partition_type: str,
        risk_level: str,
        partition_id: str,
        target_runtime: str = "python",
        failure_mode: Optional[str] = None,
        failure_mode_rules: str = "",
        complexity: float = 0.0,
        scc_id: str = "",
        translations: dict[str, str] | None = None,
        hop_cap: int = 3,
        **kwargs,
    ) -> dict:
        """Retrieve KB examples + graph context and build the prompt.

        Returns
        -------
        dict with keys:
            prompt : str
            kb_examples : list
            graph_context : list
            scc_siblings : list
            paradigm : str          — "graph"
            retrieval_k : int
            raptor_level : str      — "cluster"
        """
        # 1. Graph traversal — upstream translations + SCC siblings
        graph_context = self._get_graph_context(
            partition_id, max_hop=hop_cap, translations=translations,
        )
        scc_siblings = self._get_scc_siblings(scc_id, partition_id)

        # 2. KB retrieval at cluster level
        embedding = self.embedder.embed(source_code)
        kb_examples = self.kb.retrieve_examples(
            query_embedding=embedding,
            partition_type=partition_type,
            failure_mode=failure_mode,
            target_runtime=target_runtime,
            k=self.K,
        )

        target_label = "Python (pandas)"

        # 3. Render prompt with graph context + KB examples
        prompt = self.pm.render(
            "translation_graph",
            sas_code=source_code,
            partition_type=partition_type,
            risk_level=risk_level,
            target_label=target_label,
            complexity=complexity,
            scc_id=scc_id,
            failure_mode_rules=failure_mode_rules,
            kb_examples=kb_examples,
            graph_context=graph_context,
            scc_siblings=scc_siblings,
        )

        logger.info(
            "graph_rag_context",
            partition_type=partition_type,
            k=self.K,
            returned=len(kb_examples),
            graph_deps=len(graph_context),
            scc_siblings=len(scc_siblings),
        )

        return {
            "prompt": prompt,
            "kb_examples": kb_examples,
            "graph_context": graph_context,
            "scc_siblings": scc_siblings,
            "paradigm": self.PARADIGM_NAME,
            "retrieval_k": self.K,
            "raptor_level": "cluster",
        }
