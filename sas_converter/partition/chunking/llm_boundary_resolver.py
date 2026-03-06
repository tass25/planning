"""LLMBoundaryResolver — resolves ambiguous SAS block boundaries via an LLM.

Default provider: Azure OpenAI (GPT-4o-mini) — enterprise-grade.
Fallback chain:
    LLM_PROVIDER=azure  → Azure OpenAI GPT-4o-mini  (default, primary)
    LLM_PROVIDER=groq   → Groq Llama-3.1-8b-instant (fallback, 30 RPM limit)

Required env vars per provider:
    azure : AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT
            AZURE_OPENAI_API_VERSION (optional, default: 2024-10-21)
            AZURE_OPENAI_DEPLOYMENT_MINI (optional, default: gpt-4o-mini)
            AZURE_OPENAI_DEPLOYMENT_FULL (optional, default: gpt-4o)
    groq  : GROQ_API_KEY   (https://console.groq.com)
            GROQ_MODEL     (optional, default: llama-3.1-8b-instant)
"""

from __future__ import annotations

import os
from uuid import UUID

from pydantic import BaseModel

from partition.models.enums import PartitionType

from .models import BlockBoundaryEvent


class LLMBoundaryResponse(BaseModel):
    """Typed response from the LLM boundary resolver."""
    block_type: str
    line_end: int
    confidence: float


class LLMBoundaryResolver:
    """Resolve ambiguous block boundaries using an LLM.

    Provider selected via LLM_PROVIDER env var:
        ``"azure"``  (default) — Azure OpenAI GPT-4o-mini, requires AZURE_OPENAI_* vars
        ``"groq"``   — Groq API (fallback), requires GROQ_API_KEY
    """

    MAX_TOKENS = 6_000
    DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"

    def __init__(self, trace_id: UUID | None = None) -> None:
        self.trace_id = trace_id
        self._provider = os.getenv("LLM_PROVIDER", "azure").lower()

    # ── Public API ────────────────────────────────────────────────────────────

    async def resolve(self, event: BlockBoundaryEvent) -> BlockBoundaryEvent:
        """Re-classify an ambiguous BlockBoundaryEvent using an LLM.

        Args:
            event: An event flagged ``is_ambiguous=True``.

        Returns:
            Updated event with ``boundary_method`` set to the provider name.

        Raises:
            RuntimeError: When the LLM call fails after all retries.
        """
        if self._provider == "azure":
            return await self._resolve_azure(event)
        # Default: Groq
        return await self._resolve_groq(event)

    # ── Groq (default — fast, free tier) ────────────────────────────────────────────

    async def _resolve_groq(self, event: BlockBoundaryEvent) -> BlockBoundaryEvent:
        try:
            import instructor
            import tiktoken
        except ImportError as exc:
            raise RuntimeError(
                "groq / instructor / tiktoken not installed. "
                "Run: pip install groq instructor tiktoken"
            ) from exc

        from partition.utils.llm_clients import get_groq_client, get_groq_model

        groq_client = get_groq_client(async_client=True)
        model = get_groq_model()
        tokenizer = tiktoken.get_encoding("cl100k_base")
        raw_code  = _truncate(event.raw_code, tokenizer, self.MAX_TOKENS - 500)

        client = instructor.from_groq(groq_client, mode=instructor.Mode.JSON)

        resp: LLMBoundaryResponse = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _build_prompt(raw_code)}],
            response_model=LLMBoundaryResponse,
            max_retries=3,
        )

        return _apply_response(event, resp, method="groq")

    # ── Azure OpenAI (default — GPT-4o-mini, enterprise SLA) ────────────────

    async def _resolve_azure(self, event: BlockBoundaryEvent) -> BlockBoundaryEvent:
        try:
            import instructor
            import tiktoken
        except ImportError as exc:
            raise RuntimeError(
                "openai / instructor / tiktoken not installed. "
                "Run: pip install openai instructor tiktoken"
            ) from exc

        from partition.utils.llm_clients import get_azure_openai_client, get_deployment_name

        azure_client = get_azure_openai_client(async_client=True)
        deploy = get_deployment_name("mini")

        tokenizer = tiktoken.get_encoding("cl100k_base")
        raw_code  = _truncate(event.raw_code, tokenizer, self.MAX_TOKENS - 500)

        client = instructor.from_openai(azure_client)

        resp: LLMBoundaryResponse = await client.chat.completions.create(
            model=deploy,
            messages=[{"role": "user", "content": _build_prompt(raw_code)}],
            response_model=LLMBoundaryResponse,
            max_retries=3,
        )

        return _apply_response(event, resp, method="azure")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _truncate(code: str, tokenizer, max_tokens: int) -> str:
    tokens = tokenizer.encode(code)
    if len(tokens) <= max_tokens:
        return code
    return tokenizer.decode(tokens[:max_tokens]) + "\n... [TRUNCATED]"


def _build_prompt(raw_code: str) -> str:
    return f"""Analyze this SAS code block and determine its exact type and boundaries.

SAS Code:
```sas
{raw_code}
```

Determine the block type from:
- DATA_STEP        : starts with DATA, ends with RUN;
- PROC_BLOCK       : PROC (not SQL), ends with RUN; or QUIT;
- SQL_BLOCK        : PROC SQL, ends with QUIT;
- MACRO_DEFINITION : %MACRO ... %MEND
- MACRO_INVOCATION : %macroname(...) call
- CONDITIONAL_BLOCK: %IF/%THEN/%ELSE outside PROC
- LOOP_BLOCK       : %DO/%END iterative
- GLOBAL_STATEMENT : OPTIONS, LIBNAME, FILENAME, TITLE
- INCLUDE_REFERENCE: %INCLUDE

Respond with JSON only:
{{"block_type": "...", "line_end": <integer>, "confidence": <0.0-1.0>}}"""


def _apply_response(
    event: BlockBoundaryEvent,
    resp: LLMBoundaryResponse,
    method: str,
) -> BlockBoundaryEvent:
    try:
        event.partition_type = PartitionType(resp.block_type)
    except ValueError:
        pass  # Keep original type if LLM returns unknown value
    event.line_end        = resp.line_end
    event.confidence      = resp.confidence
    event.boundary_method = method
    event.is_ambiguous    = False
    return event
