"""Local GGUF model client — wraps llama-cpp-python.

Serves the fine-tuned Qwen2.5-Coder-7B-SAS model locally.
Provides an OpenAI-compatible interface so TranslationAgent
doesn't need to change.

Usage:
    # Set in .env:
    # LOCAL_MODEL_PATH=models/codara-qwen2.5-coder-sas-Q4_K_M.gguf

    client = LocalModelClient()
    result = await client.complete("Convert this SAS code...", max_tokens=512)
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LocalCompletion:
    """Mirrors OpenAI ChatCompletion structure."""
    content: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    model: str = "local-qwen2.5-coder-sas"


class LocalModelClient:
    """llama-cpp-python wrapper with OpenAI-compatible interface.

    Lazy-loads the model on first use (model file is ~4.5 GB).
    Subsequent calls use the cached Llama instance.

    Thread safety: asyncio.to_thread() bridges the sync llama_cpp
    API into the async pipeline without blocking the event loop.
    A 5-minute hard timeout prevents stalled CPU/GPU inference from
    hanging the pipeline indefinitely.
    """

    _llm = None  # cached Llama instance (lazy-loaded on first call)

    SYSTEM_PROMPT = (
        "You are an expert SAS-to-Python migration engineer. "
        "Convert the given SAS code to clean, idiomatic Python. "
        "Preserve all semantics exactly: variable naming, missing value "
        "handling, BY-group processing, RETAIN behaviour, and PROC equivalents."
    )

    def __init__(self) -> None:
        from config.settings import settings
        self.model_path = settings.local_model_path or os.getenv("LOCAL_MODEL_PATH", "")
        self.n_threads = settings.local_model_threads
        self.n_ctx = settings.local_model_ctx
        self._available: Optional[bool] = None

    @property
    def is_available(self) -> bool:
        """True if a model path is configured and the file exists."""
        if self._available is None:
            self._available = bool(self.model_path) and os.path.exists(self.model_path)
            if not self._available:
                logger.info(
                    "local_model_unavailable",
                    path=self.model_path or "(not set)",
                    hint="Set LOCAL_MODEL_PATH in .env after downloading the GGUF",
                )
        return self._available

    def _load_model(self) -> None:
        """Load the GGUF model (blocking — called inside asyncio.to_thread)."""
        if self._llm is not None:
            return
        try:
            from llama_cpp import Llama  # type: ignore[import]

            logger.info("local_model_loading", path=self.model_path)
            t0 = time.monotonic()
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_gpu_layers=-1,   # -1 = use GPU if available, else CPU
                verbose=False,
                chat_format="chatml",  # Qwen2.5 uses ChatML format
            )
            elapsed = time.monotonic() - t0
            logger.info("local_model_loaded", seconds=f"{elapsed:.1f}")
        except ImportError:
            raise RuntimeError(
                "llama-cpp-python is not installed. "
                "Run: pip install llama-cpp-python"
            )

    def _run_inference(
        self,
        sas_code: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> LocalCompletion:
        """Synchronous inference — must be called inside asyncio.to_thread."""
        self._load_model()

        t0 = time.monotonic()
        response = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Convert this SAS code to Python:\n\n```sas\n{sas_code}\n```",
                },
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["```\n\n", "<|im_end|>"],
        )
        elapsed_ms = (time.monotonic() - t0) * 1000

        choices = response.get("choices", [])
        if not choices:
            raise RuntimeError("Local model returned empty choices list")
        content = choices[0]["message"]["content"]
        usage = response.get("usage", {})

        return LocalCompletion(
            content=content,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            latency_ms=elapsed_ms,
        )

    async def complete(
        self,
        sas_code: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> Optional[LocalCompletion]:
        """Async wrapper — bridges sync llama_cpp into async pipeline."""
        if not self.is_available:
            return None
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._run_inference, sas_code, max_tokens, temperature),
                timeout=300,  # 5-min hard cap — GGUF can stall on overloaded CPU/GPU
            )
            logger.info(
                "local_model_complete",
                latency_ms=f"{result.latency_ms:.0f}",
                tokens=result.completion_tokens,
            )
            return result
        except asyncio.TimeoutError:
            logger.error("local_model_timeout", timeout_s=300)
            return None
        except Exception as exc:
            logger.error("local_model_error", error=str(exc))
            return None


# Module-level singleton
_client: Optional[LocalModelClient] = None


def get_local_model_client() -> LocalModelClient:
    """Return the module-level LocalModelClient singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = LocalModelClient()
    return _client
