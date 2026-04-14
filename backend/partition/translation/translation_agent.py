"""TranslationAgent (#12) — L3

Converts SAS partitions to Python using:
1. Failure-mode detection (6 rules)
2. Three RAG paradigms: Static (LOW), GraphRAG (deps/SCC), Agentic (MOD/HIGH)
3. LLM routing: Ollama (primary) → Azure (fallback) → Groq (last resort)
4. Cross-verification (Prompt C): Ollama → Groq
5. SCC batching for circular dependencies
6. Reflexion-style retry with self-reflection on failure

Provider chain (all tiers): Ollama minimax-m2.7/qwen3-coder → Azure GPT-4o → Groq LLaMA-70B.
"""

from __future__ import annotations

import uuid
import asyncio
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
    get_combined_failure_mode_rules,
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
    get_ollama_client,
    get_ollama_model,
    GroqPool,
)
from partition.utils.local_model_client import get_local_model_client

logger = structlog.get_logger()


class TranslationOutput(BaseModel):
    python_code: str = Field(..., description="Translated Python code")
    imports_detected: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    notes: str = Field(default="")


class CrossVerifyOutput(BaseModel):
    equivalent: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)


_LLM_TIMEOUT_S = 60  # per asyncio.to_thread call
_GROQ_MODEL = "llama-3.3-70b-versatile"


class TranslationAgent(BaseAgent):
    """Agent #12: SAS → Python translation.

    Routing (Ollama-first):
      - LOW risk → Ollama (primary) → Azure GPT-4o-mini → Groq
      - MODERATE/HIGH/UNCERTAIN → Ollama (primary) → Azure GPT-4o → Groq
      - Cross-verify → Ollama → Groq (independent context)

    Fallback chain: Ollama → Azure → Groq → PARTIAL status
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

        # Ollama (PRIMARY) — minimax-m2.7:cloud / qwen3-coder-next
        _ollama = get_ollama_client(async_client=False)
        self.ollama_client = (
            instructor.from_openai(_ollama) if _ollama else None
        )

        # Azure OpenAI (fallback 1) — GPT-4o / GPT-4o-mini
        try:
            self.azure_client = instructor.from_openai(
                get_azure_openai_client(async_client=False)
            )
        except RuntimeError:
            self.azure_client = None

        # Groq (fallback 2) — llama-3.3-70b, round-robin key pool
        self._groq_pool = GroqPool()
        self.groq_client = self._groq_pool if self._groq_pool.available else None
        _groq = get_groq_openai_client(async_client=False)
        self._groq_raw = _groq

        # Tier 0: local fine-tuned GGUF (free, only for LOW risk)
        self.local_client = get_local_model_client()

    async def process(self, partition: PartitionIR) -> ConversionResult:
        """Translate a single partition using the 3-tier RAG paradigm."""
        trace_id = uuid.uuid4()

        # Step 1: Detect all failure modes (returns combined rules for the prompt)
        failure_mode = detect_failure_mode(partition.source_code)  # kept for RAG routing
        fm_rules = get_combined_failure_mode_rules(partition.source_code)

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
                elif self.local_client.is_available:
                    translation, model_used = await self._translate_local(
                        partition.source_code, prompt
                    )
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
        if not self._groq_raw:
            return error_description  # graceful fallback
        try:
            resp = await asyncio.wait_for(
                asyncio.to_thread(
                    self._groq_raw.chat.completions.create,
                    model=_GROQ_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=512,
                ),
                timeout=_LLM_TIMEOUT_S,
            )
            if not resp.choices or not resp.choices[0].message.content:
                return error_description
            return resp.choices[0].message.content
        except Exception as exc:
            logger.warning("reflection_failed", error=str(exc))
            return error_description

    async def _translate_local(
        self, sas_code: str, prompt: str
    ) -> tuple[TranslationOutput, str]:
        """Tier 0: translate using local fine-tuned GGUF (LOW risk only).

        Falls back to Azure mini if the local model returns None or fails.
        """
        result = await self.local_client.complete(sas_code, max_tokens=1024)
        if result is not None:
            # Wrap raw text into TranslationOutput (local model doesn't use instructor)
            python_code = result.content.strip()
            # Strip markdown fences if present
            if python_code.startswith("```"):
                lines = python_code.split("\n")
                python_code = "\n".join(
                    line for line in lines
                    if not line.startswith("```")
                ).strip()
            imports = [
                ln.strip()
                for ln in python_code.split("\n")
                if ln.strip().startswith(("import ", "from "))
            ]
            return (
                TranslationOutput(
                    python_code=python_code,
                    imports_detected=imports,
                    confidence=0.80,
                    notes="local fine-tuned model",
                ),
                "local_qwen25",
            )
        # Local model unavailable at runtime — fall through to Azure mini
        return await self._translate_azure_mini(prompt)

    def _sync_create(self, client, **kwargs) -> TranslationOutput:
        """Thin wrapper for sync instructor/pool call (used by asyncio.to_thread).

        Accepts either an instructor-wrapped client (has .chat.completions.create)
        or a GroqPool (has .call_with_rotation).
        """
        if isinstance(client, GroqPool):
            return client.call_with_rotation(**kwargs)
        return client.chat.completions.create(**kwargs)

    async def _translate_with_model(
        self,
        prompt: str,
        azure_tier: str,
        azure_label: str,
        log_tag: str,
    ) -> tuple[TranslationOutput, str]:
        """Translate a partition. Chain: Ollama → Azure → Groq.

        Args:
            prompt:      Rendered Jinja2 prompt string.
            azure_tier:  "full" or "mini" — selects the Azure deployment.
            azure_label: Label stored in ConversionResult.model_used.
            log_tag:     Short string used in warning log keys.
        """
        messages = [{"role": "user", "content": prompt}]

        # 1. Ollama (primary)
        if self.ollama_client:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._sync_create,
                        self.ollama_client,
                        model=get_ollama_model(),
                        messages=messages,
                        response_model=TranslationOutput,
                        max_retries=2,
                    ),
                    timeout=_LLM_TIMEOUT_S,
                )
                return result, f"ollama_{get_ollama_model()}"
            except Exception as exc:
                logger.warning(f"ollama_{log_tag}_failed", error=str(exc))

        # 2. Azure (fallback)
        if self.azure_client and azure_breaker.allow_request():
            try:
                async with azure_limiter:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._sync_create,
                            self.azure_client,
                            model=get_deployment_name(azure_tier),
                            messages=messages,
                            response_model=TranslationOutput,
                            max_retries=2,
                        ),
                        timeout=_LLM_TIMEOUT_S,
                    )
                    azure_breaker.record_success()
                    return result, azure_label
            except Exception as exc:
                azure_breaker.record_failure()
                logger.warning(f"azure_{log_tag}_failed", error=str(exc))

        # 3. Groq (last resort)
        if self.groq_client:
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self._sync_create,
                    self.groq_client,
                    model=_GROQ_MODEL,
                    messages=messages,
                    response_model=TranslationOutput,
                    max_retries=2,
                ),
                timeout=_LLM_TIMEOUT_S,
            )
            return result, "groq_70b"

        raise RuntimeError("No LLM backend available for translation")

    async def _translate_azure_4o(self, prompt: str) -> tuple[TranslationOutput, str]:
        """Translate MOD/HIGH risk partitions (Ollama→Azure GPT-4o→Groq)."""
        return await self._translate_with_model(
            prompt, azure_tier="full", azure_label="azure_gpt4o", log_tag="4o"
        )

    async def _translate_azure_mini(self, prompt: str) -> tuple[TranslationOutput, str]:
        """Translate LOW risk partitions (Ollama→Azure GPT-4o-mini→Groq)."""
        return await self._translate_with_model(
            prompt, azure_tier="mini", azure_label="azure_gpt4o_mini", log_tag="mini"
        )

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
        messages = [{"role": "user", "content": prompt}]

        # 1. Ollama (primary)
        if self.ollama_client:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        self._sync_create,
                        self.ollama_client,
                        model=get_ollama_model(),
                        messages=messages,
                        response_model=CrossVerifyOutput,
                        max_retries=2,
                    ),
                    timeout=_LLM_TIMEOUT_S,
                )
            except Exception as exc:
                logger.warning("crossverify_ollama_failed", error=str(exc))

        # 2. Groq (fallback — independent context for cross-verify)
        if self.groq_client:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        self._sync_create,
                        self._groq_pool,
                        model=_GROQ_MODEL,
                        messages=messages,
                        response_model=CrossVerifyOutput,
                        max_retries=2,
                    ),
                    timeout=_LLM_TIMEOUT_S,
                )
            except Exception as exc:
                logger.warning("crossverify_groq_failed", error=str(exc))

        return None
