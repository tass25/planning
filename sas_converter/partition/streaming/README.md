# L2-B Streaming Layer

Async line-by-line file streaming with FSM-based parsing state tracking and adaptive backpressure.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 5 | `StreamAgent` | `stream_agent.py` | Async file reader — coalesces continuation lines, pushes `LineChunk` to queue |
| 6 | `StateAgent` | `state_agent.py` | Pure-Python FSM — tracks block type, nesting depth, macro stack, comment/string state |

## Files

| File | Description |
|------|-------------|
| `models.py` | `LineChunk` (coalesced SAS statement) + `ParsingState` (FSM snapshot) — Pydantic models |
| `stream_agent.py` | Async producer using `aiofiles`; handles SAS continuation lines; pushes to `asyncio.Queue` |
| `state_agent.py` | Deterministic FSM parser — no LLM, no I/O. Tracks implicit/explicit close, nesting, macro scope |
| `backpressure.py` | Adaptive queue sizing: >500MB → 10, >100MB → 50, else → 200 |
| `pipeline.py` | Producer/consumer wiring: `StreamAgent` → Queue → `StateAgent` → `list[tuple[LineChunk, ParsingState]]` |

## Architecture

```
FileMetadata (from L2-A)
        |
        v
  StreamAgent (#5)  [async producer]
    -> aiofiles line-by-line read
    -> Coalesce continuation lines (trailing &)
    -> Push LineChunk to asyncio.Queue
        |
        v  asyncio.Queue (adaptive backpressure)
        |
  StateAgent (#6)  [consumer]
    -> Pure FSM: block_type, nesting_depth, macro_stack
    -> Tracks comment/string state, implicit/explicit close
        |
        v
  list[tuple[LineChunk, ParsingState]]  -> Chunking Layer (L2-C)
```

## Key Features

- **Zero-copy streaming** — processes files line-by-line without loading into memory
- **Adaptive backpressure** — queue size scales with file size to prevent OOM
- **SAS continuation handling** — coalesces multi-line statements joined by `&`
- **Pure deterministic FSM** — StateAgent uses no LLM, fully reproducible

## Dependencies

`aiofiles`, `asyncio`, `re`, `pydantic`, `structlog`
