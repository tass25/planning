"""LLMBoundaryResolver — resolves ambiguous SAS block boundaries via an LLM.

Default provider: Groq (llama-3.1-8b-instant) — fast, free tier, OpenAI-compatible.
Upgrade paths:
    LLM_PROVIDER=azure  → Azure OpenAI GPT-4o  (see azure_evaluation.md §1)
    LLM_PROVIDER=ollama → local Ollama         (set OLLAMA_HOST + OLLAMA_MODEL)

Required env vars per provider:
    groq  : GROQ_API_KEY   (https://console.groq.com)
            GROQ_MODEL     (optional, default: llama-3.1-8b-instant)
    azure : AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY
            AZURE_OPENAI_DEPLOY (optional, default: gpt-4o)
    ollama: OLLAMA_HOST    (optional, default: http://localhost:11434)
            OLLAMA_MODEL   (optional, default: llama3.1:8b)
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
        ``"groq"``   (default) — Groq API, requires GROQ_API_KEY
        ``"azure"``  — Azure OpenAI GPT-4o, requires AZURE_OPENAI_* vars
        ``"ollama"`` — local Ollama (future), requires OLLAMA_* vars
    """

    MAX_TOKENS = 6_000
    DEFAULT_GROQ_MODEL = "llama-3.1-8b-instant"

    def __init__(self, trace_id: UUID | None = None) -> None:
        self.trace_id = trace_id
        self._provider = os.getenv("LLM_PROVIDER", "groq").lower()

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
        if self._provider == "ollama":
            return await self._resolve_ollama(event)
        # Default: Groq
        return await self._resolve_groq(event)

    # ── Groq (default — fast, free tier) ────────────────────────────────────────────

    async def _resolve_groq(self, event: BlockBoundaryEvent) -> BlockBoundaryEvent:
        try:
            import instructor
            from groq import AsyncGroq
            import tiktoken
        except ImportError as exc:
            raise RuntimeError(
                "groq / instructor / tiktoken not installed. "
                "Run: pip install groq instructor tiktoken"
            ) from exc

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY environment variable not set. "
                "Get a free key at https://console.groq.com"
            )

        model = os.getenv("GROQ_MODEL", self.DEFAULT_GROQ_MODEL)
        tokenizer = tiktoken.get_encoding("cl100k_base")
        raw_code  = _truncate(event.raw_code, tokenizer, self.MAX_TOKENS - 500)

        groq_client = AsyncGroq(api_key=api_key)
        client = instructor.from_groq(groq_client, mode=instructor.Mode.JSON)

        resp: LLMBoundaryResponse = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _build_prompt(raw_code)}],
            response_model=LLMBoundaryResponse,
            max_retries=3,
        )

        return _apply_response(event, resp, method="groq")

    # ── Ollama (future option — LLM_PROVIDER=ollama) ───────────────────────────

    async def _resolve_ollama(self, event: BlockBoundaryEvent) -> BlockBoundaryEvent:
        try:
            import instructor
            from ollama import AsyncClient
            import tiktoken
        except ImportError as exc:
            raise RuntimeError(
                "Ollama / instructor / tiktoken not installed. "
                "Run: pip install ollama instructor tiktoken"
            ) from exc

        host  = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
        tokenizer = tiktoken.get_encoding("cl100k_base")
        raw_code  = _truncate(event.raw_code, tokenizer, self.MAX_TOKENS - 500)

        client = instructor.from_openai(
            AsyncClient(host=host),
            mode=instructor.Mode.JSON,
        )

        resp: LLMBoundaryResponse = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _build_prompt(raw_code)}],
            response_model=LLMBoundaryResponse,
            max_retries=3,
        )

        return _apply_response(event, resp, method="llm_8b")

    # ── Azure OpenAI (upgrade path — azure_evaluation.md §1) ─────────────────

    async def _resolve_azure(self, event: BlockBoundaryEvent) -> BlockBoundaryEvent:
        try:
            from openai import AsyncAzureOpenAI
            import instructor
            import tiktoken
        except ImportError as exc:
            raise RuntimeError(
                "openai / instructor / tiktoken not installed. "
                "Run: pip install openai instructor tiktoken"
            ) from exc

        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
        api_key  = os.environ["AZURE_OPENAI_KEY"]
        deploy   = os.getenv("AZURE_OPENAI_DEPLOY", "gpt-4o")

        tokenizer = tiktoken.get_encoding("cl100k_base")
        raw_code  = _truncate(event.raw_code, tokenizer, self.MAX_TOKENS - 500)

        azure_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version="2024-02-01",
        )
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
