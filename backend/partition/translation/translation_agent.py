"""TranslationAgent (#12) — L3

Converts SAS partitions to Python using:
1. Failure-mode detection (6 rules)
2. Three RAG paradigms: Static (LOW), GraphRAG (deps/SCC), Agentic (MOD/HIGH)
3. LLM routing: Azure GPT-4o → Nemotron (Ollama) → Groq LLaMA-70B
4. Cross-verification (Prompt C): Azure → Groq (independent context)
5. SCC batching for circular dependencies
6. Reflexion-style retry with self-reflection on failure

Provider chain (primary → fallback 1 → fallback 2):
  Tier 1 — Azure GPT-4o / GPT-4o-mini    (PRIMARY)
  Tier 2 — Ollama nemotron-3-super:cloud  (fallback 1)
  Tier 3 — Groq LLaMA-3.3-70B            (fallback 2 + cross-verifier)
  Tier 4 — PARTIAL status                 (all tiers exhausted)
"""

from __future__ import annotations

import re
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
from partition.translation.deterministic_translator import try_deterministic
from partition.translation.macro_expander import expand_macros
from partition.translation.format_mapper import get_format_hint_block
from partition.translation.sas_builtins import get_builtins_hint_block
from partition.translation.sas_type_inferencer import infer_types
from partition.translation.kb_query import KBQueryClient
from partition.raptor.embedder import get_embedder
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


_LLM_TIMEOUT_S   = 60                       # per asyncio.to_thread call
_GROQ_MODEL      = "llama-3.3-70b-versatile"
_NEMOTRON_MODEL  = "nemotron-3-super:cloud"  # PRIMARY Ollama model (Tier 1)


class TranslationAgent(BaseAgent):
    """Agent #12: SAS → Python translation.

    LLM routing (Azure primary):
      - LOW risk              → Azure GPT-4o-mini → Nemotron → Groq
      - MODERATE/HIGH/UNCERTAIN → Azure GPT-4o → Nemotron → Groq
      - Cross-verify (Prompt C) → Azure → Groq (independent context)

    Full fallback chain: Azure → Nemotron (Ollama) → Groq → PARTIAL status
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
        self.embedder = get_embedder()   # shared singleton — not loaded per agent
        self.kb_client = KBQueryClient()
        self.prompt_manager = PromptManager()
        self.rag_router = RAGRouter(
            kb_client=self.kb_client,
            embedder=self.embedder,
            prompt_manager=self.prompt_manager,
        )
        # Translation context: stores completed translations for GraphRAG
        self._translations: dict[str, str] = {}
        # Translation memory cache: semantic fingerprint → ConversionResult
        # Avoids redundant LLM calls for structurally identical SAS patterns.
        self._translation_cache: dict[str, str] = {}

        # Azure OpenAI (PRIMARY) — GPT-4o / GPT-4o-mini
        try:
            self.azure_client = instructor.from_openai(
                get_azure_openai_client(async_client=False)
            )
        except RuntimeError:
            self.azure_client = None

        # Ollama/Nemotron (fallback 1) — nemotron-3-super:cloud
        _ollama = get_ollama_client(async_client=False)
        self.ollama_client = (
            instructor.from_openai(_ollama) if _ollama else None
        )

        # Groq (fallback 2) — llama-3.3-70b, round-robin key pool
        self._groq_pool = GroqPool()
        self.groq_client = self._groq_pool if self._groq_pool.available else None
        _groq = get_groq_openai_client(async_client=False)
        self._groq_raw = _groq

        # Tier 0: local fine-tuned GGUF (free, only for LOW risk)
        self.local_client = get_local_model_client()

    async def process(self, partition: PartitionIR) -> ConversionResult:
        """Translate a single partition using the 3-tier RAG paradigm.

        Pipeline:
          0. Deterministic shortcut — skip LLM for well-known patterns.
          1. Failure mode detection.
          2. Business logic enrichment + SAS contract extraction.
          3. RAG Router → prompt building (with enrichment + contracts injected).
          4. LLM translation (Nemotron → Azure → Groq).
          5. Cross-verify + Reflexion retry.
        """
        trace_id = uuid.uuid4()

        # ── Step 0a: Translation memory — check semantic fingerprint cache ───
        fingerprint = _semantic_fingerprint(partition.source_code)
        if fingerprint in self._translation_cache:
            cached_code = _apply_var_renaming(
                self._translation_cache[fingerprint],
                partition.source_code,
            )
            if cached_code:
                logger.info(
                    "translation_cache_hit",
                    block_id=str(partition.block_id),
                    fingerprint=fingerprint,
                )
                imports = [
                    ln.strip() for ln in cached_code.split("\n")
                    if ln.strip().startswith(("import ", "from "))
                ]
                return ConversionResult(
                    conversion_id=uuid.uuid4(),
                    block_id=partition.block_id,
                    file_id=partition.file_id,
                    python_code=cached_code,
                    imports_detected=imports,
                    status=ConversionStatus.SUCCESS,
                    llm_confidence=0.95,
                    failure_mode_flagged="",
                    model_used="translation_memory",
                    kb_examples_used=[],
                    retry_count=0,
                    trace_id=trace_id,
                    rag_paradigm="cache",
                )

        # ── Step 0b: %LET macro expansion (before deterministic translator) ──
        expanded_sas, macro_report = expand_macros(partition.source_code)
        effective_sas = expanded_sas  # use expanded code for all downstream steps

        # ── Step 0c: Deterministic shortcut (no LLM needed) ──────────────────
        det = try_deterministic(effective_sas)
        if det:
            logger.info(
                "deterministic_translation",
                block_id=str(partition.block_id),
                rule=det.reason,
            )
            imports = [
                ln.strip() for ln in det.code.split("\n")
                if ln.strip().startswith(("import ", "from "))
            ]
            return ConversionResult(
                conversion_id=uuid.uuid4(),
                block_id=partition.block_id,
                file_id=partition.file_id,
                python_code=det.code,
                imports_detected=imports,
                status=ConversionStatus.SUCCESS,
                llm_confidence=1.0,
                failure_mode_flagged="",
                model_used=f"deterministic:{det.reason}",
                kb_examples_used=[],
                retry_count=0,
                trace_id=trace_id,
                rag_paradigm="deterministic",
            )

        # ── Step 1: Failure mode detection ───────────────────────────────────
        failure_mode = detect_failure_mode(effective_sas)
        fm_rules     = get_combined_failure_mode_rules(effective_sas)

        # ── Step 2: Business logic enrichment + SAS contract extraction ──────
        business_logic = _enrich_business_logic(effective_sas, partition.partition_type.value)
        sas_contract   = _extract_sas_contract(effective_sas)

        # ── Step 2b: Format, built-in, type hints (new research modules) ─────
        format_hint  = get_format_hint_block(effective_sas)
        builtin_hint = get_builtins_hint_block(effective_sas)
        type_report  = infer_types(effective_sas)
        type_hint    = type_report.to_prompt_block()
        macro_hint   = macro_report.to_prompt_block() if macro_report.has_substitutions else ""

        # Inject enrichment and contract into metadata for RAG prompt building
        partition.metadata.setdefault("business_logic", business_logic)
        if sas_contract:
            partition.metadata.setdefault("sas_contract", sas_contract)

        # Inject error analysis hint from pipeline retry (if present)
        error_analysis_hint = partition.metadata.pop("error_analysis_hint", "")
        error_category      = partition.metadata.pop("error_category", "")

        # ── Step 3: RAG Router — select paradigm + retrieve + build prompt ───
        rag_ctx = self.rag_router.build_context(
            partition=partition,
            target_runtime=self.target_runtime,
            failure_mode=failure_mode.value if failure_mode else None,
            failure_mode_rules=fm_rules,
            attempt_number=0,
            translations=self._translations,
        )
        prompt      = rag_ctx["prompt"]
        kb_examples = rag_ctx["kb_examples"]
        paradigm    = rag_ctx["paradigm"]

        # Append all enrichment blocks to the prompt
        for block in (sas_contract, format_hint, builtin_hint, type_hint,
                      macro_hint, error_analysis_hint):
            if block:
                prompt = prompt + "\n\n" + block

        # ── Step 4: LLM translation ───────────────────────────────────────────
        model_used  = ""
        translation = None
        retry_count = 0

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if partition.risk_level.value in ("HIGH", "UNCERTAIN"):
                    # Multi-agent debate: two independent translations, Groq judges
                    translation, model_used = await self._translate_with_debate(prompt)
                elif partition.risk_level.value == "MODERATE":
                    translation, model_used = await self._translate_high_risk(prompt)
                elif self.local_client.is_available:
                    translation, model_used = await self._translate_local(
                        partition.source_code, prompt
                    )
                else:
                    translation, model_used = await self._translate_low_risk(prompt)
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
                    translation, model_used = await self._translate_high_risk(
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

        # Store successful translation for GraphRAG context + translation memory
        if status == ConversionStatus.SUCCESS:
            self._translations[str(partition.block_id)] = translation.python_code
            # Cache by semantic fingerprint for future identical-structure SAS blocks
            if fingerprint and fingerprint not in self._translation_cache:
                self._translation_cache[fingerprint] = translation.python_code

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

    async def _translate_with_debate(
        self, prompt: str
    ) -> tuple[TranslationOutput, str]:
        """Multi-agent debate for HIGH/UNCERTAIN risk partitions.

        Pattern from Du et al. "Improving Factuality and Reasoning in Language
        Models through Multiagent Debate" (ICML 2023).

        Strategy:
          1. Run Nemotron and Azure GPT-4o in parallel (independent contexts).
          2. Send both candidates to Groq as judge with the original prompt.
          3. Judge picks the semantically correct candidate (or synthesises).

        Falls back to standard _translate_high_risk if either provider fails
        or Groq is unavailable.
        """
        messages = [{"role": "user", "content": prompt}]

        # Run two independent translations concurrently
        results = await asyncio.gather(
            self._run_translation_safe(
                self.azure_client, get_deployment_name("full"), messages, "azure_debate"
            ),
            self._run_translation_safe(
                self.ollama_client, _NEMOTRON_MODEL, messages, "nemotron_debate"
            ),
            return_exceptions=True,
        )

        candidate_a: Optional[TranslationOutput] = results[0] if not isinstance(results[0], Exception) else None
        candidate_b: Optional[TranslationOutput] = results[1] if not isinstance(results[1], Exception) else None

        # If we have two valid candidates and Groq is available — run debate
        if candidate_a and candidate_b and self.groq_client:
            judge_prompt = (
                f"{prompt}\n\n"
                "## Translation Debate\n"
                "Two independent translations have been produced. "
                "Select the more semantically correct one or synthesise the best parts.\n\n"
                "### Candidate A (Azure GPT-4o)\n"
                f"```python\n{candidate_a.python_code}\n```\n\n"
                "### Candidate B (Nemotron)\n"
                f"```python\n{candidate_b.python_code}\n```\n\n"
                "Output the best translation as your `python_code` field. "
                "Set `notes` to a one-sentence explanation of why you chose/synthesised this."
            )
            try:
                judged = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._sync_create,
                        self.groq_client,
                        model=_GROQ_MODEL,
                        messages=[{"role": "user", "content": judge_prompt}],
                        response_model=TranslationOutput,
                        max_retries=1,
                    ),
                    timeout=_LLM_TIMEOUT_S,
                )
                logger.info("debate_judged", notes=judged.notes[:80] if judged.notes else "")
                return judged, "debate:azure+nemotron→groq"
            except Exception as exc:
                logger.warning("debate_judge_failed", error=str(exc))

        # Fallback: return whichever candidate exists, else standard chain
        if candidate_a:
            return candidate_a, "azure_gpt4o"
        if candidate_b:
            return candidate_b, f"ollama_{_NEMOTRON_MODEL}"

        # Full fallback to standard high-risk chain
        return await self._translate_high_risk(prompt)

    async def _run_translation_safe(
        self,
        client: Optional[object],
        model: str,
        messages: list[dict],
        label: str,
    ) -> Optional[TranslationOutput]:
        """Run a single translation attempt; return None on any failure."""
        if client is None:
            return None
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._sync_create,
                    client,
                    model=model,
                    messages=messages,
                    response_model=TranslationOutput,
                    max_retries=1,
                ),
                timeout=_LLM_TIMEOUT_S,
            )
        except Exception as exc:
            logger.warning(f"{label}_failed", error=str(exc))
            return None

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
        # Local model unavailable at runtime — fall through to low-risk chain
        return await self._translate_low_risk(prompt)

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
        """Translate a partition. Chain: Nemotron → Azure → Groq.

        Args:
            prompt:      Rendered Jinja2 prompt string.
            azure_tier:  "full" or "mini" — selects the Azure deployment.
            azure_label: Label stored in ConversionResult.model_used.
            log_tag:     Short string used in warning log keys.
        """
        messages = [{"role": "user", "content": prompt}]

        # 1. Azure (primary) — GPT-4o / GPT-4o-mini
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

        # 2. Nemotron (fallback 1) — nemotron-3-super:cloud via Ollama
        if self.ollama_client:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._sync_create,
                        self.ollama_client,
                        model=_NEMOTRON_MODEL,
                        messages=messages,
                        response_model=TranslationOutput,
                        max_retries=2,
                    ),
                    timeout=_LLM_TIMEOUT_S,
                )
                return result, f"ollama_{_NEMOTRON_MODEL}"
            except Exception as exc:
                logger.warning(f"nemotron_{log_tag}_failed", error=str(exc))

        # 3. Groq (last resort) — llama-3.3-70b
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

    async def _translate_high_risk(self, prompt: str) -> tuple[TranslationOutput, str]:
        """Translate MOD/HIGH/UNCERTAIN risk partitions (Nemotron→Azure GPT-4o→Groq)."""
        return await self._translate_with_model(
            prompt, azure_tier="full", azure_label="azure_gpt4o", log_tag="high"
        )

    async def _translate_low_risk(self, prompt: str) -> tuple[TranslationOutput, str]:
        """Translate LOW risk partitions (Nemotron→Azure GPT-4o-mini→Groq)."""
        return await self._translate_with_model(
            prompt, azure_tier="mini", azure_label="azure_gpt4o_mini", log_tag="low"
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

        # 1. Azure (primary — independent context for cross-verify)
        if self.azure_client and azure_breaker.allow_request():
            try:
                async with azure_limiter:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            self._sync_create,
                            self.azure_client,
                            model=get_deployment_name("full"),
                            messages=messages,
                            response_model=CrossVerifyOutput,
                            max_retries=2,
                        ),
                        timeout=_LLM_TIMEOUT_S,
                    )
                    azure_breaker.record_success()
                    return result
            except Exception as exc:
                azure_breaker.record_failure()
                logger.warning("crossverify_azure_failed", error=str(exc))

        # 2. Groq (fallback — independent context for cross-verify)
        if self.groq_client:
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(
                        self._sync_create,
                        self.groq_client,
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


# ── Module-level helpers (outside class) ─────────────────────────────────────

import hashlib as _hashlib

# ── Translation memory helpers ────────────────────────────────────────────────

_SAS_KEYWORDS = frozenset({
    "data", "set", "run", "proc", "by", "where", "if", "then", "else",
    "merge", "keep", "drop", "rename", "output", "retain", "array",
    "do", "end", "to", "while", "until", "return", "link", "goto",
    "input", "cards", "datalines", "infile", "file", "put", "get",
    "select", "when", "otherwise", "format", "informat", "label",
    "length", "attrib", "missing", "options", "libname", "filename",
    "ods", "title", "footnote", "global", "local", "let", "macro",
    "mend", "call", "symput", "symget", "sum", "mean", "max", "min",
    "class", "var", "model", "weight", "freq", "id", "tables", "ways",
    "nodupkey", "nodup", "sort", "import", "export", "print", "means",
    "freq", "sql", "transpose", "report", "tabulate", "sgplot",
    "connect", "execute", "create", "insert", "update", "delete",
    "from", "join", "left", "right", "inner", "outer", "on", "as",
    "order", "group", "having", "distinct", "into", "quit",
})


def _semantic_fingerprint(sas_code: str) -> str:
    """Compute a structural fingerprint of SAS code for translation memory.

    Normalises by:
    1. Removing comments and formatting
    2. Lowercasing
    3. Alpha-renaming all non-keyword identifiers to v1, v2, ...

    Two SAS blocks that differ only in variable/dataset names produce the
    same fingerprint and share a cached translation.
    """
    # Strip comments
    code = re.sub(r"/\*.*?\*/", "", sas_code, flags=re.DOTALL)
    code = re.sub(r"^\s*\*[^;]*;", "", code, flags=re.MULTILINE)
    code = re.sub(r"\s+", " ", code).strip().lower()

    # Alpha-rename non-keyword identifiers
    name_map: dict[str, str] = {}
    counter = 0

    def rename(m: re.Match) -> str:
        nonlocal counter
        tok = m.group(0)
        if tok in _SAS_KEYWORDS:
            return tok
        if tok not in name_map:
            counter += 1
            name_map[tok] = f"v{counter}"
        return name_map[tok]

    normalized = re.sub(r"\b[a-z_]\w*\b", rename, code)
    return _hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _apply_var_renaming(
    cached_python: str, new_sas: str
) -> Optional[str]:
    """Apply variable name substitution from cached translation to new SAS context.

    Builds a mapping from the cached SAS variable names to the new SAS
    variable names, then renames identifiers in the cached Python code.

    Returns None if mapping cannot be reliably constructed (conservative —
    prefer LLM re-translation over a corrupt cached result).
    """
    # Extract variable names from new SAS (non-keywords, in order of appearance)
    new_sas_clean = re.sub(r"/\*.*?\*/", "", new_sas, flags=re.DOTALL).lower()
    new_names = list(dict.fromkeys(
        m.group(0) for m in re.finditer(r"\b[a-z_]\w*\b", new_sas_clean)
        if m.group(0) not in _SAS_KEYWORDS
    ))

    # Extract variable names from cached Python code
    py_names = list(dict.fromkeys(
        m.group(0) for m in re.finditer(r"\b[a-z_]\w*\b", cached_python)
        if not m.group(0).startswith(("import", "from", "def", "class",
                                       "return", "if", "else", "for", "while",
                                       "in", "not", "and", "or", "is", "True",
                                       "False", "None", "lambda", "pd", "np"))
    ))

    # Heuristic: if name counts differ too much, don't attempt renaming
    if abs(len(new_names) - len(py_names)) > max(3, len(new_names) // 2):
        return None

    # Build substitution map (align by position)
    mapping = {}
    for old, new in zip(py_names, new_names):
        if old != new:
            mapping[old] = new

    if not mapping:
        return cached_python   # identical variable names — direct reuse

    # Apply substitution (whole-word only)
    result = cached_python
    for old, new in mapping.items():
        result = re.sub(r"\b" + re.escape(old) + r"\b", new, result)

    return result


# ── Business logic enrichment ─────────────────────────────────────────────────

_PROC_HINTS: dict[str, str] = {
    "PROC SORT":       "Sorts the dataset by the BY variables.",
    "PROC MEANS":      "Computes descriptive statistics (mean, min, max, std, n).",
    "PROC FREQ":       "Produces frequency tables and cross-tabulations.",
    "PROC SQL":        "Executes SQL queries against SAS datasets.",
    "PROC IMPORT":     "Imports an external file (CSV, Excel) into a SAS dataset.",
    "PROC EXPORT":     "Exports a SAS dataset to an external file (CSV, Excel).",
    "PROC TRANSPOSE":  "Transposes rows to columns or columns to rows.",
    "PROC PRINT":      "Prints observations from a dataset.",
    "PROC UNIVARIATE": "Detailed univariate statistics and distribution tests.",
    "PROC REG":        "Fits a linear regression model.",
    "PROC LOGISTIC":   "Fits a logistic regression model.",
    "PROC REPORT":     "Generates a customised tabular report.",
    "PROC TABULATE":   "Creates multi-dimensional summary tables.",
    "PROC SGPLOT":     "Creates statistical graphics (line, scatter, bar, etc.).",
    "DATA STEP":       "Processes data row by row, creating or transforming datasets.",
    "%MACRO":          "Defines a reusable macro (parametrised code template).",
}


def _enrich_business_logic(sas_code: str, partition_type: str) -> str:
    """Heuristic business-logic summary for a SAS chunk.

    Returns a plain-English one-liner describing what the block does.
    This is injected into the RAG prompt to improve KB retrieval quality
    without requiring an extra LLM call.
    """
    code_upper = sas_code.upper()

    # Identify the dominant PROC or block type
    for proc_name, hint in _PROC_HINTS.items():
        if re.search(proc_name.replace(" ", r"\s+"), code_upper):
            # Try to extract the primary dataset name
            ds_m = re.search(r"DATA\s*=\s*([A-Za-z0-9_.]+)", sas_code, re.IGNORECASE)
            ds = ds_m.group(1).lower().split(".")[-1] if ds_m else "dataset"
            return f"{hint} Applied to `{ds}`."

    # Fallback by partition_type
    pt_hints = {
        "DATA_STEP":        "Transforms, filters, or merges data row-by-row.",
        "PROC_BLOCK":       "Runs a SAS procedure to compute or output results.",
        "MACRO_DEFINITION": "Defines a reusable macro template.",
        "MACRO_INVOCATION": "Calls a previously defined macro with parameters.",
        "SQL_BLOCK":        "Executes a PROC SQL block with joins, aggregations, or DDL.",
        "CONDITIONAL_BLOCK":"Contains conditional macro logic (%IF/%ELSE).",
        "LOOP_BLOCK":       "Contains an iterative macro loop (%DO/%END).",
        "GLOBAL_STATEMENT": "Sets global options, libnames, or macro variables.",
        "INCLUDE_REFERENCE": "Includes an external SAS file.",
    }
    return pt_hints.get(partition_type, "Transforms SAS data.")


def _extract_sas_contract(sas_code: str) -> str:
    """Extract hard constraints from SAS source code as a prompt block.

    Extracts: BY variables, KEEP/DROP columns, MERGE type, sort direction.
    Returns a Markdown block to append to the LLM prompt, or empty string.
    """
    lines: list[str] = []

    # BY variables
    by_m = re.search(r"\bby\s+([^;]+);", sas_code, re.IGNORECASE)
    if by_m:
        by_vars = re.split(r"\s+", by_m.group(1).strip())
        by_vars = [v.lower() for v in by_vars if v and v.lower() != "descending"]
        if by_vars:
            lines.append(f"- **BY variables** (sort key / group key): `{by_vars}`")

    # KEEP
    keep_m = re.search(r"\bkeep\s+([^;]+);", sas_code, re.IGNORECASE)
    if keep_m:
        cols = [c.lower() for c in re.split(r"\s+", keep_m.group(1).strip()) if c]
        lines.append(f"- **KEEP** (output must contain exactly): `{cols}`")

    # DROP
    drop_m = re.search(r"\bdrop\s+([^;]+);", sas_code, re.IGNORECASE)
    if drop_m:
        cols = [c.lower() for c in re.split(r"\s+", drop_m.group(1).strip()) if c]
        lines.append(f"- **DROP** (must not appear in output): `{cols}`")

    # MERGE type
    if re.search(r"\bmerge\b", sas_code, re.IGNORECASE):
        has_in = bool(re.search(r"\bin=\w+", sas_code, re.IGNORECASE))
        if has_in:
            if re.search(r"if\s+\w+\s+and\s+\w+", sas_code, re.IGNORECASE):
                merge_how = "inner (both tables must match)"
            else:
                merge_how = "left or outer (unmatched rows kept)"
        else:
            merge_how = "outer (all rows kept)"
        lines.append(f"- **MERGE type** → `{merge_how}` (use appropriate `how=` in pd.merge)")

    # DESCENDING sort
    if re.search(r"\bdescending\b", sas_code, re.IGNORECASE):
        desc_m = re.findall(r"descending\s+(\w+)", sas_code, re.IGNORECASE)
        if desc_m:
            lines.append(f"- **DESCENDING** columns (use `ascending=False`): `{[c.lower() for c in desc_m]}`")

    # NODUPKEY
    if re.search(r"\bnodupkey\b", sas_code, re.IGNORECASE):
        lines.append("- **NODUPKEY**: apply `.drop_duplicates(subset=by_vars)` after sorting")

    if not lines:
        return ""

    return "## SAS Contract (hard constraints — must be satisfied)\n" + "\n".join(lines)
