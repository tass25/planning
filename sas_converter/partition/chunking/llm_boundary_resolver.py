"""LLMBoundaryResolver — resolves ambiguous SAS block boundaries via Ollama.

Uses Ollama llama3.1:8b with instructor for typed JSON output.
Falls back gracefully when Ollama is unavailable.

Azure OpenAI upgrade path:
    Set env var LLM_PROVIDER=azure and configure AZURE_OPENAI_* variables
    (see azure_evaluation.md §1) to route ambiguous blocks to GPT-4o instead.
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
    """Resolve ambiguous block boundaries using a local LLM (Ollama).

    Configuration via environment variables:
        LLM_PROVIDER        : ``"ollama"`` (default) or ``"azure"``
        OLLAMA_HOST         : default ``http://localhost:11434``
        OLLAMA_MODEL        : default ``llama3.1:8b``
        AZURE_OPENAI_ENDPOINT: required when LLM_PROVIDER=azure
        AZURE_OPENAI_KEY    : required when LLM_PROVIDER=azure
        AZURE_OPENAI_DEPLOY : deployment name, default ``gpt-4o``
    """

    MAX_TOKENS = 6_000
    DEFAULT_MODEL = "llama3.1:8b"

    def __init__(self, trace_id: UUID | None = None) -> None:
        self.trace_id = trace_id
        self._provider = os.getenv("LLM_PROVIDER", "ollama").lower()

    # ── Public API ────────────────────────────────────────────────────────────

    async def resolve(self, event: BlockBoundaryEvent) -> BlockBoundaryEvent:
        """Re-classify an ambiguous BlockBoundaryEvent using an LLM.

        Args:
            event: An event flagged ``is_ambiguous=True``.

        Returns:
            Updated event with ``boundary_method="llm_8b"`` (or ``"azure"``).

        Raises:
            RuntimeError: When the LLM call fails after all retries.
        """
        if self._provider == "azure":
            return await self._resolve_azure(event)
        return await self._resolve_ollama(event)

    # ── Ollama (local, week 3-4 default) ─────────────────────────────────────

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
        model = os.getenv("OLLAMA_MODEL", self.DEFAULT_MODEL)

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
