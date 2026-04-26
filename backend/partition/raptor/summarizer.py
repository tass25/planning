"""ClusterSummarizer — 3-tier LLM fallback for cluster summarization.

Migration note (Week 9):
    Previously: Groq Llama-3.1-70B (Tier 1) → Ollama (Tier 2) → heuristic (Tier 3)
    Now:        Azure OpenAI GPT-4o (Tier 1) → Groq (Tier 2)  → heuristic (Tier 3)

    Migrated to Azure OpenAI because:
    - Groq 30 RPM rate limit bottlenecked RAPTOR summarization on large corpora
    - GPT-4o provides superior structured-output compliance for Pydantic models
    - Azure $100 student credit covers full project usage
    - Enterprise SLA (99.9%) vs Groq free tier (best-effort)
"""

from __future__ import annotations

import hashlib
import os
import re

import structlog

try:
    import tiktoken as _tiktoken

    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _tiktoken = None  # type: ignore[assignment]
    _TIKTOKEN_AVAILABLE = False

from partition.utils.retry import azure_breaker, groq_breaker

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Pydantic output model — defined without instructor dependency so tests can
# import ClusterSummary even when instructor is not installed.
# ---------------------------------------------------------------------------
try:
    from pydantic import BaseModel, Field

    class ClusterSummary(BaseModel):
        """Structured LLM output for a cluster of SAS code blocks."""

        summary: str = Field(
            ...,
            description=(
                "A concise summary (2-3 sentences) of what this group of "
                "SAS code blocks does together."
            ),
        )
        key_constructs: list[str] = Field(
            default_factory=list,
            description=(
                "Key SAS constructs found in this cluster (e.g., DATA step, PROC SQL, macro)."
            ),
        )
        estimated_complexity: str = Field(
            default="MODERATE",
            description="LOW | MODERATE | HIGH",
        )

except ImportError:
    # Minimal fallback (should never happen in production)
    class ClusterSummary:  # type: ignore[no-redef]
        def __init__(self, summary, key_constructs=None, estimated_complexity="MODERATE"):
            self.summary = summary
            self.key_constructs = key_constructs or []
            self.estimated_complexity = estimated_complexity


# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------


class ClusterSummarizer:
    """Summarize a cluster of SAS code blocks — three-tier fallback.

    Tier 1 — Azure OpenAI GPT-4o  (primary, enterprise SLA, $100 student credit)
    Tier 2 — Groq Llama-3.1-70B   (fallback, 30 RPM rate limit)
    Tier 3 — Heuristic             (keyword extraction, no LLM needed)

    A tiktoken guard (cl100k_base) truncates prompts to MAX_PROMPT_TOKENS
    before calling any LLM tier.  cl100k_base over-estimates Llama tokens by
    ~5 %, keeping us safely within context limits.

    Results are cached by SHA-256(sorted blocks) to avoid re-summarising
    identical clusters.
    """

    MAX_PROMPT_TOKENS = 4_000
    ENCODING_NAME = "cl100k_base"

    def __init__(self):
        self._summary_cache: dict[str, ClusterSummary] = {}
        self._enc = _tiktoken.get_encoding(self.ENCODING_NAME) if _TIKTOKEN_AVAILABLE else None
        self.azure_client = None
        self.groq_client = None
        self._azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_FULL", "gpt-4o")

        try:
            import instructor

            from partition.utils.llm_clients import (
                get_azure_openai_client,
                get_groq_openai_client,
            )

            # Tier 1: Azure OpenAI (primary)
            try:
                self.azure_client = instructor.from_openai(
                    get_azure_openai_client(async_client=False)
                )
                logger.info("summarizer_tier1_ready", provider="azure_openai")
            except RuntimeError:
                pass  # env vars missing — skip Azure tier

            # Tier 2: Groq (fallback)
            _groq = get_groq_openai_client(async_client=False)
            if _groq:
                self.groq_client = instructor.from_openai(_groq)
                logger.info("summarizer_tier2_ready", provider="groq")

        except ImportError:
            logger.warning(
                "summarizer_llm_unavailable",
                msg="instructor/openai not installed — heuristic fallback only",
            )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def summarize(self, code_blocks: list[str]) -> tuple[ClusterSummary, str]:
        """Summarize a cluster of code blocks.

        Returns:
            (summary, tier) where tier is one of:
            "groq" | "ollama_fallback" | "heuristic_fallback" | "cached"
        """
        cache_key = hashlib.sha256("||".join(sorted(code_blocks)).encode()).hexdigest()

        if cache_key in self._summary_cache:
            logger.debug("summary_cache_hit", key=cache_key[:12])
            return self._summary_cache[cache_key], "cached"

        truncated = self._truncate_to_token_limit(code_blocks)
        prompt = self._build_prompt(truncated)

        # Tier 1: Azure OpenAI GPT-4o (primary)
        if self.azure_client and azure_breaker.allow_request():
            try:
                result = self.azure_client.chat.completions.create(
                    model=self._azure_deployment,
                    messages=[{"role": "user", "content": prompt}],
                    response_model=ClusterSummary,
                    max_retries=2,
                )
                azure_breaker.record_success()
                self._summary_cache[cache_key] = result
                return result, "azure_openai"
            except Exception as exc:
                azure_breaker.record_failure()
                logger.warning("azure_summary_failed", error=str(exc))

        # Tier 2: Groq Llama-3.1-70B (fallback)
        if self.groq_client and groq_breaker.allow_request():
            try:
                result = self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    response_model=ClusterSummary,
                    max_retries=2,
                )
                groq_breaker.record_success()
                self._summary_cache[cache_key] = result
                return result, "groq_fallback"
            except Exception as exc:
                groq_breaker.record_failure()
                logger.warning("groq_summary_failed", error=str(exc))

        # Tier 3: Heuristic
        result = self._heuristic_summary(code_blocks)
        self._summary_cache[cache_key] = result
        return result, "heuristic_fallback"

    @property
    def cache_size(self) -> int:
        """Absolute number of cached summaries."""
        return len(self._summary_cache)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, code_blocks: list[str]) -> str:
        blocks_text = "\n---\n".join(
            f"Block {i + 1}:\n{block}" for i, block in enumerate(code_blocks)
        )
        return (
            f"You are a SAS code analysis expert. Below are {len(code_blocks)} "
            "related SAS code blocks that belong to the same semantic cluster.\n"
            "Provide:\n"
            "1. A concise summary (2-3 sentences) of what these blocks do "
            "*together* — their collective purpose.\n"
            "2. The key SAS constructs used.\n"
            "3. An estimated complexity (LOW, MODERATE, HIGH).\n\n"
            f"{blocks_text}"
        )

    def _truncate_to_token_limit(self, code_blocks: list[str]) -> list[str]:
        """Truncate blocks to fit within MAX_PROMPT_TOKENS."""
        total_tokens = 0
        overhead = 200  # prompt template tokens
        result: list[str] = []

        for block in code_blocks:
            if self._enc is not None:
                block_tokens = len(self._enc.encode(block))
            else:
                block_tokens = len(block) // 4  # rough char-based fallback
            remaining = self.MAX_PROMPT_TOKENS - total_tokens - overhead
            if block_tokens > remaining:
                if remaining > 50:
                    if self._enc is not None:
                        tokens = self._enc.encode(block)[:remaining]
                        result.append(self._enc.decode(tokens) + "\n/* ... truncated ... */")
                    else:
                        result.append(block[: remaining * 4] + "\n/* ... truncated ... */")
                break
            result.append(block)
            total_tokens += block_tokens

        return result if result else [code_blocks[0][:500]]

    def _heuristic_summary(self, code_blocks: list[str]) -> ClusterSummary:
        """Fallback: extract SAS keywords and structure statistics."""
        all_code = "\n".join(code_blocks)
        constructs: set[str] = set()

        patterns = {
            "DATA step": r"\bDATA\s+\w+",
            "PROC SQL": r"\bPROC\s+SQL\b",
            "PROC MEANS": r"\bPROC\s+MEANS\b",
            "PROC FREQ": r"\bPROC\s+FREQ\b",
            "PROC SORT": r"\bPROC\s+SORT\b",
            "PROC REG": r"\bPROC\s+REG\b",
            "PROC LOGISTIC": r"\bPROC\s+LOGISTIC\b",
            "PROC IMPORT": r"\bPROC\s+IMPORT\b",
            "Macro definition": r"%MACRO\s+\w+",
            "MERGE": r"\bMERGE\b",
            "RETAIN": r"\bRETAIN\b",
        }
        for name, pattern in patterns.items():
            if re.search(pattern, all_code, re.IGNORECASE):
                constructs.add(name)

        n_blocks = len(code_blocks)
        total_lines = sum(b.count("\n") + 1 for b in code_blocks)
        constructs_str = ", ".join(sorted(constructs)) if constructs else "general SAS code"

        summary_text = (
            f"Cluster of {n_blocks} SAS code block{'s' if n_blocks != 1 else ''} "
            f"({total_lines} total lines). "
            f"Key constructs: {constructs_str}."
        )

        complexity = "LOW" if total_lines < 50 else "MODERATE" if total_lines < 200 else "HIGH"

        return ClusterSummary(
            summary=summary_text,
            key_constructs=list(sorted(constructs)),
            estimated_complexity=complexity,
        )
