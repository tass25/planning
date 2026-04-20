"""Static RAG — fixed retrieval for simple, low-risk blocks.

Retrieves k=3 KB examples at RAPTOR leaf level with no failure-mode
filtering, no graph context, no cross-verification, no retry.
Fastest path through the translation pipeline.
"""

from __future__ import annotations

from typing import Optional

import structlog

from partition.prompts import PromptManager
from partition.raptor.embedder import NomicEmbedder
from partition.translation.kb_query import KBQueryClient

logger = structlog.get_logger()


class StaticRAG:
    """Static RAG paradigm — fixed k=3 leaf retrieval.

    Used for LOW-risk partitions without cross-file dependencies
    or SCC membership.
    """

    K = 3
    PARADIGM_NAME = "static"

    def __init__(
        self,
        kb_client: KBQueryClient | None = None,
        embedder: NomicEmbedder | None = None,
        prompt_manager: PromptManager | None = None,
    ):
        self.kb = kb_client or KBQueryClient()
        self.embedder = embedder or NomicEmbedder()
        self.pm = prompt_manager or PromptManager()

    def build_context(
        self,
        source_code: str,
        partition_type: str,
        risk_level: str,
        target_runtime: str = "python",
        failure_mode: Optional[str] = None,
        failure_mode_rules: str = "",
        complexity: float = 0.0,
        z3_repair_hint: str = "",
        **kwargs,
    ) -> dict:
        """Retrieve examples and build the translation prompt.

        Returns
        -------
        dict with keys:
            prompt : str            — rendered prompt for the LLM
            kb_examples : list      — retrieved KB examples
            paradigm : str          — "static"
            retrieval_k : int       — number of examples retrieved
            raptor_level : str      — "leaf"
        """
        embedding = self.embedder.embed(source_code)
        kb_examples = self.kb.retrieve_examples(
            query_embedding=embedding,
            partition_type=partition_type,
            failure_mode=failure_mode,
            target_runtime=target_runtime,
            k=self.K,
        )

        target_label = "Python (pandas)"

        prompt = self.pm.render(
            "translation_static",
            sas_code=source_code,
            partition_type=partition_type,
            risk_level=risk_level,
            target_label=target_label,
            complexity=complexity,
            failure_mode_rules=failure_mode_rules,
            kb_examples=kb_examples,
            z3_repair_hint=z3_repair_hint,
        )

        logger.info(
            "static_rag_context",
            partition_type=partition_type,
            k=self.K,
            returned=len(kb_examples),
        )

        return {
            "prompt": prompt,
            "kb_examples": kb_examples,
            "paradigm": self.PARADIGM_NAME,
            "retrieval_k": self.K,
            "raptor_level": "leaf",
        }
