"""Named constants for Codara — replaces magic numbers scattered across the codebase.

Import with:
    from config.constants import AZURE_MAX_COMPLETION_TOKENS, GROQ_MAX_TOKENS, ...
"""

from __future__ import annotations

# ── LLM generation limits ─────────────────────────────────────────────────────
AZURE_MAX_COMPLETION_TOKENS: int = 16_384
GROQ_MAX_TOKENS: int = 4_096   # Groq free-tier: input+output must stay ~6k tokens total
LLM_TRANSLATION_TEMPERATURE: float = 0.1

# ── Health-check timeouts (seconds) ──────────────────────────────────────────
HEALTH_CHECK_TIMEOUT_S: float = 2.0
HEALTH_OLLAMA_HTTP_TIMEOUT_S: float = 1.5

# ── SSE streaming ─────────────────────────────────────────────────────────────
SSE_MAX_EVENTS: int = 600
SSE_POLL_INTERVAL_S: float = 1.0

# ── Pipeline ──────────────────────────────────────────────────────────────────
CHECKPOINT_INTERVAL_BLOCKS: int = 50   # Redis checkpoint every N blocks
MAX_VALIDATION_RETRIES: int = 2
PARTITION_TIMEOUT_S: int = 120

# ── File upload ───────────────────────────────────────────────────────────────
UPLOAD_FILE_ID_HEX_LEN: int = 8       # f"file-{uuid4().hex[:N]}"
