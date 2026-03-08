"""TranslationAgent (#12) — L3

Converts SAS partitions to Python/PySpark using:
1. Failure-mode detection (6 rules)
2. Three RAG paradigms: Static (LOW), GraphRAG (deps/SCC), Agentic (MOD/HIGH)
3. LLM routing: LOW → Azure GPT-4o-mini, MODERATE/HIGH → Azure GPT-4o
4. Cross-verification (Prompt C via Groq)
5. SCC batching for circular dependencies
6. Reflexion-style retry with self-reflection on failure

Azure migration: Primary LLM is Azure OpenAI (GPT-4o-mini / GPT-4o).
Groq LLaMA-70B serves as fallback and cross-verifier.
"""

from __future__ import annotations

import os
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional

import instructor
from pydantic import BaseModel, Field
import structlog

from partition.base_agent import BaseAgent
from partition.models.partition_ir import PartitionIR
from partition.models.conversion_result import ConversionResult
from partition.models.enums import ConversionStatus
from partition.translation.failure_mode_detector import (
    detect_failure_mode,
    get_failure_mode_rules,
)
from partition.translation.kb_query import KBQueryClient
from partition.raptor.embedder import NomicEmbedder
from partition.rag import RAGRouter
from partition.prompts import PromptManager
from partition.utils.retry import azure_limiter, azure_breaker
from partition.utils.llm_clients import (
    get_azure_openai_client,
    get_deployment_name,
    get_groq_openai_client,
)

logger = structlog.get_logger()


class TranslationOutput(BaseModel):
    python_code: str = Field(..., description="Translated Python/PySpark code")
    imports_detected: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str = Field(default="")


class CrossVerifyOutput(BaseModel):
    equivalent: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)


class TranslationAgent(BaseAgent):
    """Agent #12: SAS → Python/PySpark translation.

    Routing (Azure-first):
      - LOW risk → Azure GPT-4o-mini (fast, cheap)
      - MODERATE/HIGH → Azure GPT-4o (higher quality)
      - Cross-verify → Groq LLaMA-70B (independent context)

    Fallback chain: Azure GPT-4o → Groq 70B → PARTIAL status
    """

    MAX_RETRIES = 2
    CROSSVERIFY_THRESHOLD = 0.75

    @property
    def agent_name(self) -> str:
        return "TranslationAgent"

    def __init__(
        self,
        target_runtime: str = "python",
    ):
        super().__init__()
        self.target_runtime = target_runtime
        self.embedder = NomicEmbedder()
        self.kb_client = KBQueryClient()
        self.prompt_manager = PromptManager()
        self.rag_router = RAGRouter(
            kb_client=self.kb_client,
            embedder=self.embedder,
            prompt_manager=self.prompt_manager,
        )
        # Translation context: stores completed translations for GraphRAG
        self._translations: dict[str, str] = {}

        # Azure OpenAI client (primary) — via shared factory
        try:
            self.azure_client = instructor.from_openai(
                get_azure_openai_client(async_client=False)
            )
        except RuntimeError:
            self.azure_client = None

        # Groq client (fallback + cross-verifier) — via shared factory
        _groq = get_groq_openai_client(async_client=False)
        self.groq_client = instructor.from_openai(_groq) if _groq else None

    async def process(self, partition: PartitionIR) -> ConversionResult:
        """Translate a single partition using the 3-tier RAG paradigm."""
        trace_id = uuid.uuid4()

        # Step 1: Detect failure mode
        failure_mode = detect_failure_mode(partition.source_code)
        fm_rules = get_failure_mode_rules(failure_mode) if failure_mode else ""

        # Step 2: RAG Router — select paradigm + retrieve + build prompt
        rag_ctx = self.rag_router.build_context(
            partition=partition,
            target_runtime=self.target_runtime,
            failure_mode=failure_mode.value if failure_mode else None,
            failure_mode_rules=fm_rules,
            attempt_number=0,
            translations=self._translations,
        )
        prompt = rag_ctx["prompt"]
        kb_examples = rag_ctx["kb_examples"]
        paradigm = rag_ctx["paradigm"]

        # Step 3: Route to LLM
        model_used = "azure_gpt4o_mini"
        translation = None
        retry_count = 0

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if partition.risk_level.value in ("MODERATE", "HIGH", "UNCERTAIN"):
                    translation, model_used = await self._translate_azure_4o(prompt)
                else:
                    translation, model_used = await self._translate_azure_mini(prompt)
                break
            except Exception as e:
                retry_count += 1
                logger.warning(
                    "translation_retry",
                    block_id=str(partition.block_id),
                    attempt=attempt + 1,
                    error=str(e),
                )
                if attempt == self.MAX_RETRIES:
                    return ConversionResult(
                        conversion_id=uuid.uuid4(),
                        block_id=partition.block_id,
                        file_id=partition.file_id,
                        python_code=(
                            f"# PARTIAL: Translation failed after {retry_count} retries\n"
                            f"# Original SAS:\n"
                            + "\n".join(
                                f"# {line}"
                                for line in partition.source_code.split("\n")
                            )
                        ),
                        imports_detected=[],
                        status=ConversionStatus.PARTIAL,
                        llm_confidence=0.0,
                        failure_mode_flagged=(
                            failure_mode.value if failure_mode else ""
                        ),
                        model_used=model_used,
                        kb_examples_used=[
                            ex["example_id"] for ex in kb_examples
                        ],
                        retry_count=retry_count,
                        trace_id=trace_id,
                        rag_paradigm=paradigm,
                    )

        # Step 4: Cross-verify (Prompt C, separate context via Groq)
        verify = await self._cross_verify(
            partition.source_code,
            translation.python_code,
            failure_mode,
        )

        status = ConversionStatus.SUCCESS
        if verify and verify.confidence < self.CROSSVERIFY_THRESHOLD:
            # Reflexion: generate reflection on why it failed, then retry
            # with Agentic RAG (escalated k + level + reflection context)
            if retry_count < self.MAX_RETRIES:
                retry_count += 1
                reflection = await self._generate_reflection(
                    partition.source_code,
                    translation.python_code,
                    "; ".join(verify.issues),
                    failure_mode,
                )
                rag_ctx = self.rag_router.build_context(
                    partition=partition,
                    target_runtime=self.target_runtime,
                    failure_mode=failure_mode.value if failure_mode else None,
                    failure_mode_rules=fm_rules,
                    attempt_number=retry_count,
                    previous_issues=verify.issues,
                    reflection=reflection,
                    error_description="; ".join(verify.issues),
                    translations=self._translations,
                )
                prompt = rag_ctx["prompt"]
                paradigm = rag_ctx["paradigm"]
                try:
                    translation, model_used = await self._translate_azure_4o(
                        prompt
                    )
                    verify = await self._cross_verify(
                        partition.source_code,
                        translation.python_code,
                        failure_mode,
                    )
                except Exception as exc:
                    self.logger.warning(
                        "retry_translation_failed",
                        error=str(exc),
                        retry=retry_count,
                    )

            if not verify or verify.confidence < self.CROSSVERIFY_THRESHOLD:
                status = ConversionStatus.PARTIAL

        # Store successful translation for GraphRAG context
        if status == ConversionStatus.SUCCESS:
            self._translations[str(partition.block_id)] = translation.python_code

        return ConversionResult(
            conversion_id=uuid.uuid4(),
            block_id=partition.block_id,
            file_id=partition.file_id,
            python_code=translation.python_code,
            imports_detected=translation.imports_detected,
            status=status,
            llm_confidence=verify.confidence if verify else translation.confidence,
            failure_mode_flagged=failure_mode.value if failure_mode else "",
            model_used=model_used,
            kb_examples_used=[ex["example_id"] for ex in kb_examples],
            retry_count=retry_count,
            trace_id=trace_id,
            rag_paradigm=paradigm,
        )

    async def _generate_reflection(
        self,
        sas_code: str,
        python_code: str,
        error_description: str,
        failure_mode: Optional[object],
    ) -> str:
        """Generate a Reflexion-style self-reflection on a failed translation.

        Uses the reflection.j2 template + Groq LLaMA-70B to analyse what
        went wrong so the next attempt receives targeted guidance.
        """
        prompt = self.prompt_manager.render(
            "reflection",
            sas_code=sas_code,
            python_code=python_code,
            error_description=error_description,
            failure_mode=failure_mode.value if failure_mode else None,
        )
        if not self.groq_client:
            return error_description  # graceful fallback
        try:
            resp = await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_retries=1,
            )
            return resp.choices[0].message.content or error_description
        except Exception as exc:
            logger.warning("reflection_failed", error=str(exc))
            return error_description

    def _sync_create(self, client, **kwargs) -> TranslationOutput:
        """Thin wrapper for sync instructor call (used by asyncio.to_thread)."""
        return client.chat.completions.create(**kwargs)

    async def _translate_azure_4o(
        self, prompt: str
    ) -> tuple[TranslationOutput, str]:
        """Translate using Azure GPT-4o (primary, high-quality)."""
        if self.azure_client and azure_breaker.allow_request():
            try:
                async with azure_limiter:
                    result = await asyncio.to_thread(
                        self._sync_create,
                        self.azure_client,
                        model=get_deployment_name("full"),
                        messages=[{"role": "user", "content": prompt}],
                        response_model=TranslationOutput,
                        max_retries=2,
                    )
                    azure_breaker.record_success()
                    return result, "azure_gpt4o"
            except Exception as e:
                azure_breaker.record_failure()
                logger.warning("azure_4o_failed", error=str(e))

        # Fallback to Groq 70B
        if self.groq_client:
            result = await asyncio.to_thread(
                self._sync_create,
                self.groq_client,
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_model=TranslationOutput,
                max_retries=2,
            )
            return result, "groq_70b"

        raise RuntimeError("No LLM backend available for translation")

    async def _translate_azure_mini(
        self, prompt: str
    ) -> tuple[TranslationOutput, str]:
        """Translate using Azure GPT-4o-mini (fast, for LOW risk)."""
        if self.azure_client and azure_breaker.allow_request():
            try:
                async with azure_limiter:
                    result = await asyncio.to_thread(
                        self._sync_create,
                        self.azure_client,
                        model=get_deployment_name("mini"),
                        messages=[{"role": "user", "content": prompt}],
                        response_model=TranslationOutput,
                        max_retries=2,
                    )
                    azure_breaker.record_success()
                    return result, "azure_gpt4o_mini"
            except Exception as e:
                azure_breaker.record_failure()
                logger.warning("azure_mini_failed", error=str(e))

        # Fallback to Groq 70B
        if self.groq_client:
            result = await asyncio.to_thread(
                self._sync_create,
                self.groq_client,
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_model=TranslationOutput,
                max_retries=2,
            )
            return result, "groq_70b"

        raise RuntimeError("No LLM backend available for translation")

    async def _cross_verify(
        self,
        sas_code: str,
        python_code: str,
        failure_mode: Optional[object],
    ) -> Optional[CrossVerifyOutput]:
        """Cross-verify SAS↔Python equivalence using Groq (independent context)."""
        prompt = self.prompt_manager.render(
            "cross_verify",
            sas_code=sas_code,
            python_code=python_code,
            failure_mode=failure_mode.value if failure_mode else None,
        )
        if not self.groq_client:
            return None
        try:
            return await asyncio.to_thread(
                self.groq_client.chat.completions.create,
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                response_model=CrossVerifyOutput,
                max_retries=2,
            )
        except Exception as e:
            logger.warning("crossverify_failed", error=str(e))
            return None
