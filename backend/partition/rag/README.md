# RAG Layer — 3-Tier Retrieval-Augmented Generation

> **Paradigms**: StaticRAG, GraphRAG, AgenticRAG  
> **Router**: RAGRouter  
> **Spec ref**: Cahier des charges §3.2  

## Overview

Three retrieval paradigms that inject contextual knowledge into translation
prompts. The `RAGRouter` selects the appropriate paradigm per partition based
on risk level, SCC membership, and dependency structure.

## Architecture

```
RAGRouter.select_paradigm(partition)
  │
  ├─ risk MOD / HIGH / UNCERTAIN  →  AgenticRAG
  ├─ has SCC / cross-file deps    →  GraphRAG
  └─ else (LOW, no deps)          →  StaticRAG
```

## Files

| File | Purpose |
|------|---------|
| `router.py` | `RAGRouter` — paradigm selection + `build_context()` dispatcher |
| `static_rag.py` | `StaticRAG` — k=3 leaf-level retrieval |
| `graph_rag.py` | `GraphRAG` — k=5 cluster-level, BFS graph context, SCC siblings |
| `agentic_rag.py` | `AgenticRAG` — adaptive k, level escalation, query reformulation |

## Paradigm Details

| Paradigm | k | RAPTOR Level | Special Features |
|----------|---|-------------|------------------|
| Static | 3 | leaf | Simple nearest-neighbor retrieval |
| Graph | 5 | cluster | BFS walk, SCC siblings, upstream translation injection |
| Agentic | adaptive | leaf→cluster→root | k escalation (+3/attempt), query reformulation, graph escalation |
