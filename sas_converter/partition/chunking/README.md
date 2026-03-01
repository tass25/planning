# L2-C Chunking Layer

Boundary detection + partition building for the RAPTOR v2 pipeline.

## Files

| File | Description |
|---|---|
| `models.py` | `BlockBoundaryEvent` — data model for a detected SAS block |
| `boundary_detector.py` | `BoundaryDetector` (deterministic) + `BoundaryDetectorAgent` (orchestrator) |
| `llm_boundary_resolver.py` | Ollama llama3.1:8b resolver for ambiguous blocks (~20%) |
| `partition_builder.py` | `PartitionBuilderAgent` — converts events to `PartitionIR` |

## Architecture

```
StreamAgent + StateAgent output
        │
        ▼  (chunks_with_states)
  BoundaryDetectorAgent
      ├── BoundaryDetector   → 80% rule-based (FSM transitions)
      └── LLMBoundaryResolver → 20% ambiguous (Ollama / Azure OpenAI)
        │
        ▼  (list[BlockBoundaryEvent])
  PartitionBuilderAgent
        │
        ▼  (list[PartitionIR])
  PersistenceAgent / IndexAgent (Week 5+)
```

## LLM Provider

Set `LLM_PROVIDER=ollama` (default) or `LLM_PROVIDER=azure` (see `azure_evaluation.md §1`).
