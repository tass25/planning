# RAPTOR — Implementation Notes & Paper Reference

## Paper

**RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval**
Sarthi et al., 2024 — Stanford NLP
arXiv: https://arxiv.org/abs/2401.18059

---

## Core Idea

Standard RAG retrieves only leaf-level chunks. RAPTOR builds a **tree of
summaries** over those chunks, so queries can match at multiple levels of
abstraction — from a single function to a whole macro framework.

```
Root summary (entire file / module)
  └── Cluster summary (group of related blocks)
        └── Leaf node (individual partition — DATA step, PROC, macro)
```

At query time, the retriever walks the tree and scores matches at all levels,
then boosts the final score based on depth (leaves scored higher than abstractions
for exact matches, roots higher for structural/architectural queries).

---

## Codara Implementation

### Files

| File | Role |
|------|------|
| `partition/raptor/raptor_agent.py` | Orchestrates the 4-step pipeline |
| `partition/raptor/embedder.py` | `NomicEmbedder` — 768-dim sentence embeddings (Nomic AI) |
| `partition/raptor/clustering.py` | `GMMClusterer` — Gaussian Mixture Model on embeddings |
| `partition/raptor/summarizer.py` | `ClusterSummarizer` — LLM summaries of each cluster |
| `partition/raptor/tree_builder.py` | `RAPTORTreeBuilder` — assembles `PartitionIR` back-links |
| `partition/raptor/lancedb_writer.py` | Writes leaf + cluster + root nodes into LanceDB |

### Differences from the Paper

| Paper | Codara adaptation |
|-------|------------------|
| Generic text chunks | `PartitionIR` objects (typed: DATA step, PROC, macro, …) |
| GMM soft clustering | Same — kept GMM, curvature flag for HyperRAPTOR (Week 15) |
| OpenAI for summaries | Azure GPT-4o-mini (Tier 0 LOW risk path) |
| Flat documents | SAS files: each file → partition → RAPTOR tree per file |
| Fixed chunk size | Variable: partition boundaries from `BoundaryDetectorAgent` |

### Tree Depth

Codara builds a **2-level tree** (leaves + one cluster level):
- Leaf = individual `PartitionIR` (one DATA step, one PROC, one macro)
- Cluster = group of thematically related partitions (same file section)
- Root = file-level summary (generated if ≥ 2 clusters)

The paper uses up to 4 levels; 2 is sufficient for SAS files which are shorter
than general-purpose documents and have explicit structural boundaries.

---

## Key Design Decisions

### Why Nomic Embeddings?

- 768-dimensional, runs on CPU (sentence-transformers)
- Strong on code + prose (SAS code is mixed: identifiers + English comments)
- Free — no API call needed, embedded at index time

### Why GMM over K-Means?

GMM (Gaussian Mixture Model) assigns **soft cluster membership** — a partition
can partially belong to multiple clusters. This is important for SAS code where
a single macro call may logically belong to both the "ETL" cluster and the
"data quality" cluster.

K-Means forces hard assignment; GMM produces overlapping clusters that better
reflect real SAS code structure.

### Skip Condition

RAPTOR skips clustering when `n_partitions < 2` (single block files).
GMM requires `n_samples >= n_components`, so minimum cluster count is
`min(n_partitions // 2, 8)`.

---

## Retrieval Integration

The RAPTOR index is queried in `partition/translation/kb_query.py` and
`partition/rag/agentic_rag.py`:

```python
# Agentic RAG: query at leaf level first, then escalate to cluster if score < threshold
leaf_results   = kb.search(embedding, level="leaf",    k=5)
cluster_results = kb.search(embedding, level="cluster", k=3)
# Combine and re-rank by (score * depth_weight)
```

---

## Evaluation Results

See `docs/ablation_results.md` for full numbers. Summary:

- RAPTOR hit-rate@5: **0.84** vs flat **0.71** (+18%)
- RAPTOR MRR: **0.63** vs flat **0.54** (+17%)
- Largest gain on HIGH-risk partitions: **+36%** hit-rate

---

## HyperRAPTOR Extension (Week 15)

Planned upgrade: replace Euclidean GMM clustering with **Poincaré ball K-means**
(hyperbolic geometry via `geoopt`). SAS code has strong hierarchical structure
(macro → PROC → DATA step) that maps naturally to a tree metric.
Enable via `USE_HYPER_RAPTOR=true` in `.env`.

Reference: Nickel & Kiela, *Poincaré Embeddings for Learning Hierarchical
Representations*, NeurIPS 2017.
