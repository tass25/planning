# RAPTOR Semantic Clustering

Recursive Abstractive Processing for Tree-Organized Retrieval (Sarthi et al.) adapted for SAS code partitions.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 10 | `RAPTORPartitionAgent` | `raptor_agent.py` | Orchestrates embed → cluster → summarize → tree-build per file |

## Files

| File | Description |
|------|-------------|
| `embedder.py` | `NomicEmbedder` — 768-dim embeddings via `nomic-ai/nomic-embed-text-v1.5`; SHA-256 cache; task prefixes |
| `clustering.py` | `GMMClusterer` — Gaussian Mixture Model with soft assignment (τ=0.72); k=√N; BIC convergence |
| `summarizer.py` | `ClusterSummarizer` — 3-tier LLM fallback: Nemotron (Ollama) → Azure GPT-4o → Groq Llama-3.3-70B → heuristic |
| `tree_builder.py` | `RAPTORTreeBuilder` — Recursive algorithm: leaf → GMM → summarize → embed → recurse; depth 3-5 |
| `lancedb_writer.py` | `RAPTORLanceDBWriter` — LanceDB persistence with Arrow schema; cosine IVF index (32 partitions) |
| `raptor_agent.py` | Orchestrates the full RAPTOR pipeline for a set of partitions |

## Architecture

```
list[PartitionIR] (from Chunking Layer)
        |
        v
  NomicEmbedder
    -> nomic-embed-text-v1.5 (768-dim)
    -> SHA-256 embedding cache
        |
        v  np.ndarray (N x 768)
  GMMClusterer
    -> Gaussian Mixture Model, k=sqrt(N)
    -> Soft assignment threshold tau=0.72
    -> BIC convergence check
        |
        v  cluster assignments
  ClusterSummarizer
    -> Nemotron (Ollama) → Azure GPT-4o → Groq 70B → heuristic fallback
    -> Pydantic structured output (ClusterSummary)
        |
        v  summaries
  RAPTORTreeBuilder
    -> Recursive: embed summaries -> cluster -> summarize -> recurse
    -> Dynamic depth: 3 (standard), 5 (macro-heavy)
    -> Produces tree of RAPTORNode
        |
        v
  RAPTORLanceDBWriter
    -> Upsert to LanceDB (raptor_nodes table)
    -> Cosine IVF index when >= 64 vectors
```

## Key Features

- **Local embeddings** — Nomic Embed runs on-device, no API calls; 768-dim dense vectors
- **Soft clustering** — GMM allows multi-cluster membership (τ=0.72 threshold)
- **Recursive tree** — Builds hierarchical abstraction layers per Sarthi et al.
- **LanceDB persistence** — Arrow-native vector store with IVF indexing
- **Graceful fallback** — LLM summarization degrades: Azure → Groq → heuristic

## Dependencies

`sentence-transformers`, `numpy`, `scikit-learn`, `lancedb`, `pyarrow`, `tiktoken`, `pydantic`, `structlog`
