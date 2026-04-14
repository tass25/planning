"""Shared LLM client factory.

Provider hierarchy (translation chain):
  Tier 0 — Local GGUF via llama-cpp-python (fine-tuned Qwen2.5-Coder, free)
  Tier 1 — Ollama minimax-m2.7:cloud / qwen3-coder-next (PRIMARY — 10/10 on torture test)
  Tier 2 — Azure OpenAI GPT-4o / GPT-4o-mini (fallback 1)
  Tier 3 — Groq Llama-3.3-70B (fallback 2 — cross-verify & last resort)
  Tier 4 — Gemini 2.0 Flash (oracle & judge)
  Tier 5 — Cerebras Llama-3.1-70B (Best-of-N candidates)
  Tier 6 — PARTIAL status

# Pattern: Strategy
LLMStrategy ABC + OllamaStrategy / AzureStrategy / GroqStrategy concrete
classes formalise the fallback chain.  FallbackChain iterates strategies
in order, returning the first successful result.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


# ── Strategy Pattern ──────────────────────────────────────────────────────────


class LLMStrategy(ABC):
    """Abstract base for a single LLM provider strategy."""

    @abstractmethod
    def get_client(self, *, async_client: bool = True) -> Any:
        """Return a configured (Async)OpenAI-compatible client or None."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the required credentials are present."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""


class OllamaStrategy(LLMStrategy):
    """Tier 1 — Ollama (local + cloud models via OpenAI-compatible API)."""

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        return bool(os.getenv("OLLAMA_API_KEY"))

    def get_client(self, *, async_client: bool = True) -> Any:
        return get_ollama_client(async_client=async_client)


class AzureStrategy(LLMStrategy):
    """Tier 2 — Azure OpenAI (GPT-4o / GPT-4o-mini)."""

    @property
    def name(self) -> str:
        return "azure"

    def is_available(self) -> bool:
        return bool(
            os.getenv("AZURE_OPENAI_ENDPOINT") and os.getenv("AZURE_OPENAI_API_KEY")
        )

    def get_client(self, *, async_client: bool = True) -> Any:
        try:
            return get_azure_openai_client(async_client=async_client)
        except RuntimeError:
            return None


class GroqStrategy(LLMStrategy):
    """Tier 3 — Groq (Llama-3.3-70B, fallback + cross-verifier)."""

    @property
    def name(self) -> str:
        return "groq"

    def is_available(self) -> bool:
        return bool(os.getenv("GROQ_API_KEY"))

    def get_client(self, *, async_client: bool = True) -> Any:
        return get_groq_openai_client(async_client=async_client)


# Pattern: Strategy — FallbackChain iterates strategies in priority order
class FallbackChain:
    """Try each LLMStrategy in order; return the first available client.

    Usage::

        chain = FallbackChain([OllamaStrategy(), AzureStrategy(), GroqStrategy()])
        client = chain.get_client()   # first available provider
        provider_name = chain.active_name
    """

    def __init__(self, strategies: list[LLMStrategy]) -> None:
        self._strategies = strategies
        self._active: LLMStrategy | None = None

    def get_client(self, *, async_client: bool = True) -> Any:
        """Return the first available client, caching the active strategy."""
        for strategy in self._strategies:
            if strategy.is_available():
                client = strategy.get_client(async_client=async_client)
                if client is not None:
                    self._active = strategy
                    return client
        logger.warning("fallback_chain_exhausted", strategies=[s.name for s in self._strategies])
        return None

    @property
    def active_name(self) -> str:
        return self._active.name if self._active else "none"


# Default chain: Ollama → Azure → Groq (matches CLAUDE.md routing)
DEFAULT_FALLBACK_CHAIN = FallbackChain(
    [OllamaStrategy(), AzureStrategy(), GroqStrategy()]
)


def get_azure_openai_client(*, async_client: bool = True):
    """Return an (Async)AzureOpenAI client configured from env vars.

    Raises RuntimeError if required env vars are missing.
    """
    from openai import AsyncAzureOpenAI, AzureOpenAI

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    if not endpoint or not api_key:
        raise RuntimeError(
            "AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY must be set. "
            "Add them to your .env file or export them."
        )
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")

    cls = AsyncAzureOpenAI if async_client else AzureOpenAI
    return cls(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )


def get_groq_client(*, async_client: bool = True):
    """Return an (Async)Groq client configured from env vars.

    Raises RuntimeError if GROQ_API_KEY is not set.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable not set. "
            "Get a free key at https://console.groq.com"
        )

    try:
        if async_client:
            from groq import AsyncGroq
            return AsyncGroq(api_key=api_key)
        else:
            from groq import Groq
            return Groq(api_key=api_key)
    except ImportError:
        raise RuntimeError(
            "The 'groq' package is not installed. "
            "Install it with: pip install groq"
        )


def get_deployment_name(tier: str = "mini") -> str:
    """Return the Azure deployment name for the given tier.

    Args:
        tier: ``"mini"`` for GPT-4o-mini, ``"full"`` for GPT-4o.
    """
    if tier == "full":
        return os.getenv("AZURE_OPENAI_DEPLOYMENT_FULL", "gpt-4o")
    return os.getenv("AZURE_OPENAI_DEPLOYMENT_MINI", "gpt-4o-mini")


def get_groq_model() -> str:
    """Return the configured Groq model name."""
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def get_groq_openai_client(*, async_client: bool = False):
    """Return an OpenAI client pointing at Groq's OpenAI-compatible endpoint.

    Returns ``None`` if ``GROQ_API_KEY`` is not set (soft fallback).
    Use this when ``instructor.from_openai()`` wrapping is required.
    """
    from openai import AsyncOpenAI, OpenAI

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    cls = AsyncOpenAI if async_client else OpenAI
    return cls(api_key=api_key, base_url="https://api.groq.com/openai/v1")


def get_all_groq_keys() -> list[str]:
    """Return all available Groq API keys (primary + rotations).

    Reads GROQ_API_KEY, GROQ_API_KEY_2, GROQ_API_KEY_3, … up to index 9.
    Skips missing / empty values.
    """
    keys: list[str] = []
    primary = os.getenv("GROQ_API_KEY", "")
    if primary:
        keys.append(primary)
    for i in range(2, 10):
        k = os.getenv(f"GROQ_API_KEY_{i}", "")
        if k:
            keys.append(k)
    return keys


class GroqPool:
    """Round-robin pool of Groq OpenAI-compatible clients.

    On a 429 rate-limit error, ``call_with_rotation`` automatically
    switches to the next API key so tests survive the 100K-token/day cap.

    Usage::

        pool = GroqPool()
        result = pool.call_with_rotation(
            model="llama-3.3-70b-versatile",
            messages=[...],
            response_model=TranslationOutput,
            max_retries=2,
        )
    """

    _GROQ_BASE = "https://api.groq.com/openai/v1"

    def __init__(self):
        import instructor
        from openai import OpenAI

        keys = get_all_groq_keys()
        if not keys:
            self._clients: list = []
            return

        self._clients = [
            instructor.from_openai(
                OpenAI(api_key=k, base_url=self._GROQ_BASE)
            )
            for k in keys
        ]
        self._index = 0
        logger.info("groq_pool_init", keys_available=len(keys))

    @property
    def available(self) -> bool:
        return len(self._clients) > 0

    def call_with_rotation(self, **kwargs):
        """Attempt the call, rotating keys on 429 rate-limit errors.

        Raises the last exception if all keys are exhausted.
        """
        from openai import RateLimitError

        if not self._clients:
            raise RuntimeError("No Groq API keys configured")

        last_exc: Exception | None = None
        for _ in range(len(self._clients)):
            client = self._clients[self._index]
            try:
                return client.chat.completions.create(**kwargs)
            except (RateLimitError, Exception) as exc:
                err_str = str(exc).lower()
                if "rate_limit" in err_str or "429" in err_str or "tokens per day" in err_str:
                    logger.warning(
                        "groq_key_rate_limited",
                        key_index=self._index,
                        rotating_to=(self._index + 1) % len(self._clients),
                    )
                    self._index = (self._index + 1) % len(self._clients)
                    last_exc = exc
                    continue
                raise  # non-429 error — propagate immediately
        raise last_exc or RuntimeError("All Groq keys exhausted")


# ── Gemini 2.0 Flash (free tier: 1M TPM/day) ─────────────────────────
def get_gemini_client(*, async_client: bool = True):
    """Return an OpenAI-compatible client pointing at Gemini.

    Uses Google's OpenAI-compatible endpoint so the rest of the codebase
    doesn't need to change.  Requires GEMINI_API_KEY env var.
    Returns None if key is missing (graceful degradation).
    """
    from openai import AsyncOpenAI, OpenAI

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("gemini_client_unavailable", reason="GEMINI_API_KEY not set")
        return None
    cls = AsyncOpenAI if async_client else OpenAI
    return cls(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )


def get_gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


# ── Cerebras (free: Llama-3.1-70B at ~2000 tok/s) ────────────────────
def get_cerebras_client(*, async_client: bool = True):
    """Return an OpenAI-compatible client pointing at Cerebras.

    Best for high-throughput Best-of-N candidate generation (free tier).
    Returns None if key is missing.
    """
    from openai import AsyncOpenAI, OpenAI

    api_key = os.getenv("CEREBRAS_API_KEY")
    if not api_key:
        logger.warning("cerebras_client_unavailable", reason="CEREBRAS_API_KEY not set")
        return None
    cls = AsyncOpenAI if async_client else OpenAI
    return cls(
        api_key=api_key,
        base_url="https://api.cerebras.ai/v1",
    )


def get_cerebras_model() -> str:
    return os.getenv("CEREBRAS_MODEL", "llama3.1-70b")


# ── Ollama (local + cloud models via OpenAI-compatible API) ───────────
def get_ollama_client(*, async_client: bool = True):
    """Return an OpenAI-compatible client pointing at the Ollama endpoint.

    Works for both local Ollama models and cloud models served through
    the Ollama API (qwen3-coder-next, gemma4, kimi-k2.5, etc.).
    Returns None if OLLAMA_API_KEY is missing (graceful degradation).
    """
    from openai import AsyncOpenAI, OpenAI

    api_key = os.getenv("OLLAMA_API_KEY")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    if not api_key:
        logger.warning("ollama_client_unavailable", reason="OLLAMA_API_KEY not set")
        return None
    cls = AsyncOpenAI if async_client else OpenAI
    return cls(api_key=api_key, base_url=base_url, timeout=300.0)


# ── Ollama model name constants ───────────────────────────────────────
# Use OLLAMA_MODEL env var to switch at runtime.  Defaults to
# qwen3-coder-next which scored best on the torture_test benchmark.
OLLAMA_MODEL_MINIMAX    = "minimax-m2.7:cloud"    # 10/10 torture test (2026-04-06)
OLLAMA_MODEL_QWEN3      = "qwen3-coder-next"       # strong reasoning, recommended default
OLLAMA_MODEL_DEEPSEEK   = "deepseek-v3.2"          # DeepSeek V3.2 via Ollama cloud


def get_ollama_model() -> str:
    """Return the configured Ollama model name (default: qwen3-coder-next).

    Override at runtime with the OLLAMA_MODEL env var.  Known good values:
      - ``minimax-m2.7:cloud``  — 10/10 on torture test
      - ``qwen3-coder-next``    — strong reasoning, recommended default
      - ``deepseek-v3.2``       — DeepSeek V3.2 (alternative)
    """
    return os.getenv("OLLAMA_MODEL", OLLAMA_MODEL_QWEN3)


def get_ollama_model_for_tier(tier: str) -> str:
    """Return the Ollama model for a specific translation tier.

    Allows using different models per risk level:
      - ``low``    → OLLAMA_MODEL_LOW  (default: qwen3-coder-next)
      - ``high``   → OLLAMA_MODEL_HIGH (default: qwen3-coder-next)
      - default    → OLLAMA_MODEL (global override)

    This supports A/B testing between minimax, qwen3, and deepseek.
    """
    tier_key = f"OLLAMA_MODEL_{tier.upper()}"
    tier_model = os.getenv(tier_key)
    if tier_model:
        return tier_model
    return get_ollama_model()
