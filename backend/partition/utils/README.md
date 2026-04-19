# `partition/utils/` — Robustness Utilities

Resilience primitives for the SAS→Python conversion pipeline.
Added in **Week 9** to harden all external API calls (Ollama, Azure OpenAI, Groq)
and protect against large-file memory exhaustion.

## Modules

| File | Purpose |
|------|---------|
| `retry.py` | `RateLimitSemaphore` (async concurrency limiter) + `CircuitBreaker` (trip-open after N failures, auto-reset) |
| `llm_clients.py` | Factory functions for Ollama, Azure OpenAI, Groq, and GroqPool clients |
| `local_model_client.py` | `LocalModelClient` — optional llama-cpp wrapper for a local GGUF model (Tier 0) |
| `large_file.py` | `detect_file_size_strategy()` (standard / large / huge), `checkpoint_interval()`, `configure_memory_guards()`, `MemoryMonitor` |

## Key Components

### RateLimitSemaphore
Async context manager that limits concurrent LLM calls:
- **Azure OpenAI**: 10 concurrent (generous student-tier limits)
- **Groq**: 3 concurrent (30 RPM free tier, conservative)

### CircuitBreaker
Three-state pattern (CLOSED → OPEN → HALF_OPEN → CLOSED):
- **Azure**: trips after 5 failures, resets after 60 s
- **Groq**: trips after 3 failures, resets after 120 s

### File-Size Strategy
| Strategy | Line Count | Checkpointing | RAPTOR |
|----------|-----------|---------------|--------|
| Standard | < 10,000 | Every 50 blocks | Full (LOW/MOD/HIGH) |
| Large | 10,000–50,000 | Every 25 blocks | Full |
| Huge | > 50,000 | Every 10 blocks | HIGH-only |

### MemoryMonitor
Uses `psutil` to track RSS memory, warns if over 100 MB limit.

## Global Instances

```python
from partition.utils.retry import azure_limiter, groq_limiter
from partition.utils.retry import azure_breaker, groq_breaker
```

## Integration Points

- `boundary_detector.py` — wraps LLM resolve calls with `azure_breaker` + `azure_limiter`
- `orchestrator.py` — calls `configure_memory_guards()` at startup, uses `MemoryMonitor`
