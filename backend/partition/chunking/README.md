# L2-C Chunking Layer

Boundary detection + partition building for SAS code blocks.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 7 | `BoundaryDetectorAgent` | `boundary_detector.py` | Deterministic (regex+FSM) + LLM boundary detection |
| 8 | `PartitionBuilderAgent` | `partition_builder.py` | Convert `BlockBoundaryEvent` → `PartitionIR` with content-hash |
| 9 | `LLMBoundaryResolver` | `llm_boundary_resolver.py` | Azure OpenAI resolver for ambiguous blocks (~20%) |

## Files

| File | Description |
|------|-------------|
| `models.py` | `BlockBoundaryEvent` Pydantic model — boundary method, confidence, line range, nesting depth |
| `boundary_detector.py` | Two-pass detection: 80% rule-based via FSM transitions, 20% LLM for ambiguous blocks (>200 lines) |
| `llm_boundary_resolver.py` | Multi-provider LLM: Azure OpenAI (primary), Groq fallback, Ollama local. Env-var configured |
| `partition_builder.py` | Builds `PartitionIR` from events, computes SHA-256 `content_hash`, leaves risk/strategy for downstream |

## Architecture

```
StreamAgent + StateAgent output (list[tuple[LineChunk, ParsingState]])
        |
        v
  BoundaryDetectorAgent
      |-- BoundaryDetector     -> 80% rule-based (FSM transitions, COVERAGE_MAP)
      +-- LLMBoundaryResolver  -> 20% ambiguous (Azure OpenAI GPT-4o-mini)
        |
        v  list[BlockBoundaryEvent]
  PartitionBuilderAgent
        |
        v  list[PartitionIR]
  (downstream: RAPTOR -> Complexity -> Persistence -> Index)
```

## LLM Provider Configuration

Azure OpenAI is the primary provider (GPT-4o-mini for LOW/MODERATE, GPT-4o for HIGH risk).

```bash
$env:AZURE_OPENAI_API_KEY = "your-key"
$env:AZURE_OPENAI_ENDPOINT = "https://your-resource.openai.azure.com/"
```

## Dependencies

`pydantic`, `structlog`, `hashlib`, `os`, `asyncio`
