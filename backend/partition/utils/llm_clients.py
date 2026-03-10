"""Shared LLM client factory — single source for Azure / Groq clients."""

from __future__ import annotations

import os
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


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

    if async_client:
        from groq import AsyncGroq
        return AsyncGroq(api_key=api_key)
    else:
        from groq import Groq
        return Groq(api_key=api_key)


def get_llm_provider() -> str:
    """Return the configured LLM provider name (azure|groq)."""
    return os.getenv("LLM_PROVIDER", "azure").lower()


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
    return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


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
