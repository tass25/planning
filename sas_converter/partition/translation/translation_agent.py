"""TranslationAgent (#12) — L3

Converts SAS partitions to Python/PySpark using:
1. Failure-mode detection (6 rules)
2. KB retrieval (LanceDB, k=5)
3. LLM routing: LOW → Azure GPT-4o-mini, MODERATE/HIGH → Azure GPT-4o
4. Cross-verification (Prompt C via Groq)
5. SCC batching for circular dependencies

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
from partition.utils.retry import azure_limiter, azure_breaker
from partition.utils.llm_clients import (
    get_azure_openai_client,
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
        """Translate a single partition."""
        trace_id = uuid.uuid4()

        # Step 1: Detect failure mode
        failure_mode = detect_failure_mode(partition.source_code)
        fm_rules = get_failure_mode_rules(failure_mode) if failure_mode else ""

        # Step 2: Retrieve KB examples
        embedding = self.embedder.embed(partition.source_code)
        kb_examples = self.kb_client.retrieve_examples(
            query_embedding=embedding,
            partition_type=partition.partition_type.value,
            failure_mode=failure_mode.value if failure_mode else None,
            target_runtime=self.target_runtime,
            k=5,
        )

        # Step 3: Build prompt
        complexity = partition.metadata.get("complexity_score", 0.5)
        prompt = self._build_prompt(partition, kb_examples, fm_rules, complexity)

        # Step 4: Route to LLM
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
                    )

        # Step 5: Cross-verify (Prompt C, separate context via Groq)
        verify = await self._cross_verify(
            partition.source_code,
            translation.python_code,
            failure_mode,
        )

        status = ConversionStatus.SUCCESS
        if verify and verify.confidence < self.CROSSVERIFY_THRESHOLD:
            if retry_count < self.MAX_RETRIES:
                retry_count += 1
                enhanced_prompt = prompt + (
                    "\n\nPREVIOUS ATTEMPT ISSUES:\n"
                    + "\n".join(verify.issues)
                    + "\nPlease fix these issues."
                )
                try:
                    translation, model_used = await self._translate_azure_4o(
                        enhanced_prompt
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
        )

    def _build_prompt(
        self,
        partition: PartitionIR,
        kb_examples: list[dict],
        fm_rules: str,
        complexity: float,
    ) -> str:
        """Build the translation prompt with few-shot examples and rules."""
        few_shot = ""
        if kb_examples:
            few_shot = "\n\n--- REFERENCE EXAMPLES ---\n"
            for i, ex in enumerate(kb_examples[:3], 1):
                few_shot += (
                    f"\nExample {i} (similarity: {ex['similarity']:.2f}):\n"
                    f"SAS:\n```sas\n{ex['sas_code']}\n```\n"
                    f"Python:\n```python\n{ex['python_code']}\n```\n"
                )

        target_label = (
            "PySpark" if self.target_runtime == "pyspark" else "Python (pandas)"
        )

        return f"""Convert the following SAS code to {target_label}.

Partition type: {partition.partition_type.value}
Risk level: {partition.risk_level.value}
Complexity score: {complexity:.2f}

SAS Code:
```sas
{partition.source_code}
```
{fm_rules}
{few_shot}

Requirements:
- Produce syntactically valid Python code
- Include all necessary import statements
- Use idiomatic {target_label} patterns
- Add brief comments for non-obvious translations
- Handle edge cases (empty DataFrames, null values)
"""

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
                        model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
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
                        model=os.getenv("AZURE_OPENAI_MINI_DEPLOYMENT", "gpt-4o-mini"),
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
        fm_check = ""
        if failure_mode:
            fm_check = (
                f"\nPay special attention to the {failure_mode.value} pattern.\n"
                "Check that the known pitfall for this pattern is correctly handled."
            )

        prompt = f"""Verify if this Python code is semantically equivalent to the SAS code.

SAS:
```sas
{sas_code}
```

Python:
```python
{python_code}
```
{fm_check}

Check for: date epoch errors, merge semantics, RETAIN behavior,
FIRST./LAST. logic, missing value comparisons, PROC MEANS output structure.
"""
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
