"""Agentic RAG — autonomous retrieval with adaptive k, level escalation,
query reformulation, and Reflexion-style retry.

The agent autonomously controls:
1. Whether to retrieve at all (UNCERTAIN → skip, emit stub)
2. How many results (adaptive k: MOD→5, HIGH→8)
3. Which RAPTOR level to query (leaf → cluster → root)
4. Whether to reformulate the query on failure
5. Whether to escalate to GraphRAG context on final retry

This is the most sophisticated RAG paradigm, reserved for MOD/HIGH risk
blocks, detected failure modes, or blocks that failed simpler paradigms.
"""

from __future__ import annotations

from typing import Optional

import structlog

from partition.prompts import PromptManager
from partition.translation.kb_query import KBQueryClient
from partition.raptor.embedder import NomicEmbedder
from partition.index.graph_builder import NetworkXGraphBuilder

logger = structlog.get_logger()

# Adaptive k by risk level
_K_BY_RISK = {
    "LOW": 5,
    "MODERATE": 5,
    "HIGH": 8,
    "UNCERTAIN": 0,
}

# RAPTOR level escalation sequence
_LEVEL_ESCALATION = ["leaf", "cluster", "root"]


class AgenticRAG:
    """Agentic RAG paradigm — autonomous retrieval control.

    Implements a multi-stage retrieval loop:
      1. Initial retrieval (leaf level, risk-adaptive k)
      2. On failure: reformulate query + escalate level + increase k by 3
      3. Final escalation: root level + graph context (hybrid GraphRAG+Agentic)
    """

    K_ESCALATION_STEP = 3
    MAX_RETRIEVAL_ATTEMPTS = 3
    PARADIGM_NAME = "agentic"

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

    def _adaptive_k(self, risk_level: str) -> int:
        return _K_BY_RISK.get(risk_level, 5)

    def _get_raptor_level(self, attempt: int) -> str:
        idx = min(attempt, len(_LEVEL_ESCALATION) - 1)
        return _LEVEL_ESCALATION[idx]

    def _reformulate_query(
        self,
        source_code: str,
        failure_mode: Optional[str],
        error_description: str,
    ) -> str:
        """Reformulate the retrieval query by appending failure context."""
        parts = [source_code]
        if failure_mode:
            parts.append(f"FAILURE_MODE: {failure_mode}")
        if error_description:
            parts.append(f"ERROR: {error_description}")
        return "\n".join(parts)

    def _get_graph_context_for_escalation(
        self,
        partition_id: str,
        translations: dict[str, str] | None = None,
    ) -> list[dict]:
        """Fetch graph context on final escalation (hybrid mode)."""
        deps = self.graph.query_dependencies(partition_id, max_hop=3)
        translations = translations or {}
        return [
            {
                "partition_id": d["partition_id"],
                "partition_type": d.get("partition_type", ""),
                "relation": "upstream",
                "python_code": translations.get(d["partition_id"], ""),
            }
            for d in deps
        ]

    def build_context(
        self,
        source_code: str,
        partition_type: str,
        risk_level: str,
        partition_id: str = "",
        target_runtime: str = "python",
        failure_mode: Optional[str] = None,
        failure_mode_rules: str = "",
        complexity: float = 0.0,
        attempt_number: int = 0,
        previous_issues: list[str] | None = None,
        reflection: str = "",
        error_description: str = "",
        translations: dict[str, str] | None = None,
        z3_repair_hint: str = "",
        **kwargs,
    ) -> dict:
        """Retrieve with adaptive k, level escalation, and query reformulation.

        Returns
        -------
        dict with keys:
            prompt : str
            kb_examples : list
            graph_context : list        — populated on final escalation
            paradigm : str              — "agentic"
            retrieval_k : int
            raptor_level : str
            attempt_number : int
        """
        # Determine adaptive k and RAPTOR level based on attempt
        base_k = self._adaptive_k(risk_level)
        current_k = base_k + (attempt_number * self.K_ESCALATION_STEP)
        raptor_level = self._get_raptor_level(attempt_number)

        # Skip retrieval for UNCERTAIN risk
        if risk_level == "UNCERTAIN":
            logger.info("agentic_rag_skip", reason="UNCERTAIN risk")
            target_label = "Python (pandas)"
            prompt = self.pm.render(
                "translation_agentic",
                sas_code=source_code,
                partition_type=partition_type,
                risk_level=risk_level,
                target_label=target_label,
                complexity=complexity,
                raptor_level="none",
                retrieval_k=0,
                attempt_number=attempt_number + 1,
                max_attempts=self.MAX_RETRIEVAL_ATTEMPTS,
                failure_mode_rules=failure_mode_rules,
                previous_issues=previous_issues or [],
                reflection=reflection,
                graph_context=[],
                kb_examples=[],
                z3_repair_hint=z3_repair_hint,
            )
            return {
                "prompt": prompt,
                "kb_examples": [],
                "graph_context": [],
                "paradigm": self.PARADIGM_NAME,
                "retrieval_k": 0,
                "raptor_level": "none",
                "attempt_number": attempt_number,
            }

        # Reformulate query on retry attempts
        if attempt_number > 0 and error_description:
            query_text = self._reformulate_query(source_code, failure_mode, error_description)
        else:
            query_text = source_code

        # Embed and retrieve
        embedding = self.embedder.embed(query_text)
        kb_examples = self.kb.retrieve_examples(
            query_embedding=embedding,
            partition_type=partition_type,
            failure_mode=failure_mode,
            target_runtime=target_runtime,
            k=current_k,
        )

        # Final escalation: inject graph context (hybrid GraphRAG+Agentic)
        graph_context = []
        if attempt_number >= 2 and partition_id:
            graph_context = self._get_graph_context_for_escalation(
                partition_id, translations=translations,
            )

        target_label = "Python (pandas)"

        prompt = self.pm.render(
            "translation_agentic",
            sas_code=source_code,
            partition_type=partition_type,
            risk_level=risk_level,
            target_label=target_label,
            complexity=complexity,
            raptor_level=raptor_level,
            retrieval_k=current_k,
            attempt_number=attempt_number + 1,
            max_attempts=self.MAX_RETRIEVAL_ATTEMPTS,
            failure_mode_rules=failure_mode_rules,
            previous_issues=previous_issues or [],
            reflection=reflection,
            graph_context=graph_context,
            kb_examples=kb_examples,
            z3_repair_hint=z3_repair_hint,
        )

        logger.info(
            "agentic_rag_context",
            partition_type=partition_type,
            risk_level=risk_level,
            k=current_k,
            level=raptor_level,
            attempt=attempt_number,
            returned=len(kb_examples),
            graph_escalated=len(graph_context) > 0,
        )

        return {
            "prompt": prompt,
            "kb_examples": kb_examples,
            "graph_context": graph_context,
            "paradigm": self.PARADIGM_NAME,
            "retrieval_k": current_k,
            "raptor_level": raptor_level,
            "attempt_number": attempt_number,
        }
