# L2-C Chunking Layer

Boundary detection + partition building for SAS code blocks.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 7 | `BoundaryDetectorAgent` | `boundary_detector.py` | Deterministic (regex+FSM) + LLM boundary detection |
| 8 | `PartitionBuilderAgent` | `partition_builder.py` | Convert `BlockBoundaryEvent` → `PartitionIR` with content-hash |
| 9 | `LLMBoundaryResolver` | `llm_boundary_resolver.py` | LLM fallback for ambiguous blocks (~20%) |

## Files

| File | Description |
|------|-------------|
| `models.py` | `BlockBoundaryEvent` Pydantic model — boundary method, confidence, line range, nesting depth |
| `boundary_detector.py` | Two-pass detection: 80% rule-based via FSM transitions, 20% LLM for ambiguous blocks (>200 lines) |
| `llm_boundary_resolver.py` | Multi-provider LLM: Ollama Nemotron (primary), Azure GPT-4o-mini, Groq fallback |
| `partition_builder.py` | Builds `PartitionIR` from events, computes SHA-256 `content_hash`, leaves risk/strategy for downstream |

## Architecture

```
StreamAgent + StateAgent output (list[tuple[LineChunk, ParsingState]])
        |
        v
  BoundaryDetectorAgent
      |-- BoundaryDetector     -> 80% rule-based (FSM transitions, COVERAGE_MAP)
      +-- LLMBoundaryResolver  -> 20% ambiguous (Nemotron → Azure → Groq)
        |
        v  list[BlockBoundaryEvent]
  PartitionBuilderAgent
        |
        v  list[PartitionIR]
  (downstream: RAPTOR -> Complexity -> Persistence -> Index)
```

## LLM Provider Configuration

Nemotron via Ollama is the primary provider, Azure and Groq are fallbacks.
Set these in your `.env` file — all three are optional at the boundary-detection
stage, which degrades gracefully to deterministic-only if none are available.

```env
OLLAMA_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434/v1
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
GROQ_API_KEY=...
```

## Dependencies

`pydantic`, `structlog`, `hashlib`, `os`, `asyncio`
