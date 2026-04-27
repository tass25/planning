# Week 5 Done: L2-E RAPTOR Semantic Clustering Layer

> **Dates**: Mar 3, 2026  
> **Layer**: L2-E (RAPTOR Tree)  
> **Branch**: `main`  
> **Commits**: `7538c7d` (repo refactor), `0898a04` (RAPTOR layer)

---

## 🎯 Objective

Implement the full RAPTOR semantic-clustering pipeline for SAS partitions:
embed every PartitionIR block with Nomic Embed v1.5, recursively GMM-cluster
embeddings with soft assignment (τ = 0.72), summarise clusters through a
3-tier LLM fallback, persist the resulting tree in LanceDB with a cosine IVF
index, and expose the whole workflow through Agent #7 (`RAPTORPartitionAgent`).

Secondary objective: clean up 50+ scattered debug scripts that had
accumulated at the repo root and inside `sas_converter/`.

---

## ✅ What Was Done

### 0. Repo Hygiene — `7538c7d`

Before writing any new code, reorganised the repo:

| Action | Detail |
|--------|--------|
| `sas_converter/scripts/debug/` | Moved 50 debug scripts (12 from repo root + 38 from `sas_converter/`) |
| `sas_converter/scripts/debug/output/` | Moved 6 `.txt` debug output files |
| `sas_converter/examples/` | Moved `demo_pipeline.py` + `test_input.sas`, fixed `sys.path` |
| Conflict resolution | 4 same-name files (different content) at both levels → root versions prefixed `v0_` |
| `.gitignore` | Added rule to ignore future `scripts/debug/output/*.txt` |
| `sas_converter/README.md` | Full rewrite: project tree, Quick Start CLI + Demo, fixed test/benchmark commands |
| New READMEs | `scripts/debug/README.md` (naming convention table), `examples/README.md` (usage docs) |

63 files changed, 408 insertions, 15 deletions.

---

### 1. `partition/models/raptor_node.py` — RAPTORNode Pydantic model

New data model for a node in the RAPTOR tree:

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | UUID | Auto-generated unique id |
| `level` | int | 0 = leaf, 1+ = cluster, max = root |
| `summary` | str | Human / LLM-generated summary |
| `summary_tier` | str | "skipped" \| "groq" \| "ollama_fallback" \| "heuristic_fallback" \| "cached" |
| `embedding` | list[float] | 768-dim Nomic vector |
| `child_ids` | list[str] | Child node UUIDs |
| `cluster_label` | int \| None | GMM cluster index |
| `file_id` | UUID | Source file reference |
| `partition_ids` | list[str] | All block_ids reachable from this node |

Extended `PartitionIR` with three back-link fields (`raptor_leaf_id`,
`raptor_cluster_id`, `raptor_root_id`) and a `has_macros` property that
checks `partition_type ∈ {MACRO_DEFINITION, MACRO_INVOCATION}`.

---

### 2. `partition/raptor/embedder.py` — NomicEmbedder

Wraps `SentenceTransformer("nomic-ai/nomic-embed-text-v1.5")` with:

- **Prefix handling**: `search_document:` for indexing, `search_query:` for retrieval (omitting degrades recall ~15%)
- **SHA-256 cache**: duplicate texts are never re-embedded
- **Batch API**: `embed_batch(texts, batch_size=32)` with progress bar for >100 texts
- **CPU/GPU**: accepts `device="cpu"` or `device="cuda"`

---

### 3. `partition/raptor/clustering.py` — GMMClusterer

GMM soft-assignment clustering per the RAPTOR paper (Sarthi et al.):

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| k | `√N` (min 2) | Auto-selects cluster count |
| τ (tau) | 0.72 | Soft-assignment threshold; a block can belong to multiple clusters |
| BIC ε | 0.01 | `|BIC_t − BIC_{t−1}| < ε` → stop recursion |
| `reg_covar` | 1e-5 | Prevents singular covariance matrices |
| retries | 3 | Shifted random seed per attempt |

Fallback: if GMM fails after 3 attempts → single cluster (flat partition).

---

### 4. `partition/raptor/summarizer.py` — ClusterSummarizer

Three-tier LLM fallback chain:

1. **Groq** Llama-3.1-70B (structured output via `instructor`)
2. **Ollama** Llama-3.1-70B local
3. **Heuristic** — keyword extraction + line-count stats, no LLM needed

Safety features:
- `tiktoken` (`cl100k_base`) guard at 4 000 tokens max per prompt
- SHA-256 result cache (sorted block content as key)
- Pydantic `ClusterSummary` response model enforces structured output

---

### 5. `partition/raptor/tree_builder.py` — RAPTORTreeBuilder

Recursive algorithm:

```
Level 0  →  Leaf nodes (one per PartitionIR, embedded)
Level 1  →  GMM cluster → summarise → embed summary → RAPTORNode
Level 2+ →  Recursion on previous level until BIC converges or k=1
Root     →  Single summary node covering the entire file
```

Dynamic depth:
- Standard files: `max_depth = 3`
- Macro-heavy files (macro_density > 0.4): `max_depth = 5`

Back-links: after tree construction, each `PartitionIR` gets its
`raptor_leaf_id`, `raptor_cluster_id`, and `raptor_root_id` populated.

---

### 6. `partition/raptor/raptor_agent.py` — RAPTORPartitionAgent (Agent #7)

Extends `BaseAgent`. Orchestrates:

```
NomicEmbedder → GMMClusterer → ClusterSummarizer → RAPTORTreeBuilder
```

- Auto-computes `macro_density` from partitions to choose tree depth.
- Graceful degradation: on exception → flat leaf-only tree (no crash).

---

### 7. `partition/raptor/lancedb_writer.py` — RAPTORLanceDBWriter

LanceDB persistence for RAPTOR nodes:

| Feature | Detail |
|---------|--------|
| Table | `raptor_nodes` (PyArrow schema, 768-dim embedding column) |
| Upsert | Create-on-first-write, append on subsequent |
| Index | Cosine IVF (`num_partitions=32`, `num_sub_vectors=16`) — auto-created when ≥ 64 rows |
| Query | `query_similar(embedding, k=5, level=…, file_id=…)` for L3 retrieval |
| Count | `count_nodes(file_id=…)` for instrumentation |

---

### 8. Dependencies Added

| Package | Version | Purpose |
|---------|---------|---------|
| sentence-transformers | ≥ 2.2 | Nomic Embed v1.5 |
| torch | ≥ 2.1 | Backend for sentence-transformers |
| lancedb | ≥ 0.4 | Vector store for RAPTOR nodes |
| pyarrow | ≥ 14.0 | LanceDB schema + Parquet |
| instructor | ≥ 1.0 | Structured LLM output (Pydantic) |
| tiktoken | ≥ 0.5 | Token counting for prompt guard |
| openai | ≥ 1.0 | OpenAI-compatible client (Groq + Ollama) |

All added to `sas_converter/requirements.txt`.

---

## 🧪 Tests — 18/18 Passing

```
tests/test_raptor.py::TestGMMClusterer::test_cluster_basic             PASSED
tests/test_raptor.py::TestGMMClusterer::test_cluster_single_sample     PASSED
tests/test_raptor.py::TestGMMClusterer::test_cluster_empty             PASSED
tests/test_raptor.py::TestGMMClusterer::test_bic_convergence_true      PASSED
tests/test_raptor.py::TestGMMClusterer::test_bic_convergence_false     PASSED
tests/test_raptor.py::TestGMMClusterer::test_soft_assignment_tau       PASSED
tests/test_raptor.py::TestGMMClusterer::test_all_samples_assigned      PASSED
tests/test_raptor.py::TestClusterSummarizer::test_heuristic_fallback   PASSED
tests/test_raptor.py::TestClusterSummarizer::test_heuristic_detects    PASSED
tests/test_raptor.py::TestClusterSummarizer::test_cache_key_determ.    PASSED
tests/test_raptor.py::TestClusterSummarizer::test_heuristic_complexity PASSED
tests/test_raptor.py::TestRAPTORNode::test_create_raptor_node          PASSED
tests/test_raptor.py::TestPartitionIRRaptorFields::test_default_none   PASSED
tests/test_raptor.py::TestPartitionIRRaptorFields::test_has_macros     PASSED
tests/test_raptor.py::TestRAPTORTreeBuilder::test_leaf_node_creation   PASSED
tests/test_raptor.py::TestRAPTORTreeBuilder::test_dynamic_depth_const  PASSED
tests/test_raptor.py::TestRAPTORTreeBuilder::test_build_tree_returns   PASSED
tests/test_raptor.py::TestRAPTORTreeBuilder::test_backlink_sets_leaf   PASSED
```

18 assertions, 0 failures, 6 ConvergenceWarnings (expected — mock data is
degenerate for GMM).

---

## 📁 Files Changed (Commit `0898a04`)

| File | Status |
|------|--------|
| `partition/models/raptor_node.py` | **NEW** |
| `partition/models/partition_ir.py` | Modified (RAPTOR back-links + `has_macros`) |
| `partition/models/__init__.py` | Modified (re-exports) |
| `partition/raptor/__init__.py` | **NEW** |
| `partition/raptor/embedder.py` | **NEW** |
| `partition/raptor/clustering.py` | **NEW** |
| `partition/raptor/summarizer.py` | **NEW** |
| `partition/raptor/tree_builder.py` | **NEW** |
| `partition/raptor/raptor_agent.py` | **NEW** |
| `partition/raptor/lancedb_writer.py` | **NEW** |
| `tests/test_raptor.py` | **NEW** |
| `requirements.txt` | Modified (+4 RAPTOR deps) |

12 files changed, 1 302 insertions, 1 deletion.

---

## 📊 Architecture State (End of Week 5)

```
Agent #1  StreamReaderAgent       ✅ (week 1)
Agent #2  FileMetadataAgent       ✅ (week 1)
Agent #3  StateAgent              ✅ (week 2)
Agent #4  BoundaryDetectorAgent   ✅ (week 2-3)
Agent #5  PartitionBuilderAgent   ✅ (week 2)
Agent #6  ComplexityAgent         ✅ (week 4)
Agent #6b StrategyAgent           ✅ (week 4)
Agent #7  RAPTORPartitionAgent    ✅ (week 5)  ← NEW
```

```
Layer  Module                 Status
L0     entry/                 ✅
L1     streaming/             ✅
L2-A   chunking/              ✅
L2-B   chunking/ (boundary)   ✅ 79.3%
L2-C   chunking/ (partition)  ✅
L2-D   complexity/            ✅
L2-E   raptor/                ✅  ← NEW
L3     persistence/           📅 week 7
```

---

## 📋 Week 5–6 Checklist Status

- [x] `partition/raptor/embedder.py` — NomicEmbedder with batch + cache + query prefix
- [x] `partition/raptor/clustering.py` — GMMClusterer with τ=0.72, k=√N, BIC convergence
- [x] `partition/raptor/summarizer.py` — ClusterSummarizer with 3-tier fallback + tiktoken guard
- [x] `partition/raptor/tree_builder.py` — RAPTORTreeBuilder with recursive levels + dynamic depth
- [x] `partition/raptor/raptor_agent.py` — RAPTORPartitionAgent (#7) wrapping all components
- [x] `partition/raptor/lancedb_writer.py` — LanceDB writer with cosine IVF index
- [x] Leaf nodes created for all partitions (level 0)
- [x] GMM clusters form at level 1 (verified in tests)
- [x] BIC convergence stops recursion (verified in tests)
- [x] Dynamic depth: max_depth=5 triggers for macro-heavy files
- [x] Summary cache hit rate mechanism (SHA-256 cache + cache_size property)
- [x] Groq → Ollama → heuristic fallback chain implemented
- [x] Tiktoken guard truncates long cluster inputs
- [x] LanceDB raptor_nodes table schema defined (PyArrow)
- [x] Cosine IVF index (num_partitions=32) auto-created
- [x] `tests/test_raptor.py` — 18 assertions passing
- [x] Git committed on `main`

---

## 💡 Key Learnings

- **Nomic Embed v1.5 requires `trust_remote_code=True`** in the SentenceTransformer constructor — without it, model loading fails silently.
- **PartitionIR field names matter**: the planning doc referenced `raw_code` and `partition_id`, but the actual PartitionIR model uses `source_code` and `block_id`. Adapting early saved refactoring time.
- **The `has_macros` property was not on PartitionIR** — implementing it as a clean `@property` derived from `partition_type` avoids adding a redundant stored field.
- **GMM ConvergenceWarning on mock data is expected** — 3 identical 768-dim vectors clustered with k=2 will always warn. The retry mechanism handles this in production (shifted seed + `reg_covar=1e-5`).
- **`cl100k_base` over-estimates Llama tokens by ~5%** — this is conservative (safe side) for the tiktoken prompt guard.

---

## � Visualization Script (Added 2026-03-03)

**File**: `planning/week05_06viz.py`

**Purpose**: RAPTOR tree structure visualization from LanceDB vector store.

**What it shows**:
- LanceDB `raptor_nodes` table query (limit 1000)
- Level distribution bar chart (0, 1, 2)
- Summary tier pie chart (groq/ollama_fallback/heuristic_fallback/cached)
- Tree structure plot with parent-child edges using Circle patches
- PCA 2D projection of 768-dim embeddings colored by tree level

**Database required**: `lancedb_data/` folder with `raptor_nodes` table

**Setup**:
```bash
# Generate dummy RAPTOR data
python populate_dummy_data.py

# OR run RAPTOR pipeline with real data (requires Week 5-6 implementation)
```

**Run**:
```bash
python planning/week05_06viz.py
```

**Output**: Text summary + matplotlib plots showing RAPTOR tree levels, embedding projection, and summary tier distribution.

---

## �🔮 What's Next (Week 7)

Per `planning/week-07.md`: **Persistence & Index Layer (L3)**.

Expected deliverables:
- DuckDB writer for partitions + file metadata
- LanceDB IVF index tuning for the full 50-file gold corpus
- End-to-end pipeline integration test (streaming → partition → RAPTOR → persist)
- Query API for the TranslationAgent to retrieve context

---

## ☁️ Azure Migration Update (Added Week 9)

### What was used before

The `ClusterSummarizer` (`partition/raptor/summarizer.py`) originally used a 3-tier LLM fallback:
1. **Tier 1 — Groq Llama-3.1-70B-versatile**: Best quality, but rate-limited to 30 RPM on the free tier
2. **Tier 2 — Ollama Llama-3.1-70B**: Local fallback, slower (~8s/call) but unlimited
3. **Tier 3 — Heuristic**: Keyword extraction, no LLM needed

Groq was chosen initially because it was the fastest free option, and Ollama as local fallback didn't require internet. The problem: on the 50-file gold standard corpus, RAPTOR generates dozens of clusters per file. Groq's 30 RPM limit meant summarization alone could take 15+ minutes with constant retry backoffs.

### Why we migrated to Azure OpenAI

1. **Rate limit elimination**: Azure OpenAI has no hard RPM cap on student tier — the 30 RPM Groq bottleneck vanishes.
2. **GPT-4o for summarization**: GPT-4o produces significantly better cluster summaries than Llama-3.1-70B. The structured output (`ClusterSummary` Pydantic model) has fewer parse failures.
3. **Cost-effective**: GPT-4o at ~$5/M input tokens. The entire gold corpus summarization costs ~$0.15. The $100 student credit covers the full internship.
4. **Consistent with boundary resolver**: Using Azure OpenAI for both chunking (GPT-4o-mini) and RAPTOR (GPT-4o) simplifies credential management — one set of `AZURE_OPENAI_*` env vars.
5. **Ollama dropped from fallback chain**: Ollama required a local 70B model download (~40GB). Groq replaces it as Tier 2 fallback.

### What changed

| Change | Detail |
|--------|--------|
| Tier 1 | Groq Llama-3.1-70B → **Azure OpenAI GPT-4o** |
| Tier 2 | Ollama local → **Groq Llama-3.1-70B** (fallback) |
| Tier 3 | Heuristic (unchanged) |
| Constructor | Added `azure_endpoint`, `azure_api_key`, `azure_api_version`, `azure_deployment` params |
| Auto-config | Reads `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT_FULL` from env |
| Return tier | `"azure_openai"` (new) or `"groq_fallback"` (renamed from `"groq"`) or `"heuristic_fallback"` |
| Import | Added `os` import, `from openai import AzureOpenAI` alongside existing `OpenAI` |

### New fallback chain

```
Azure OpenAI GPT-4o  →  Groq Llama-3.1-70B  →  Heuristic (keyword extraction)
     (primary)             (fallback)              (offline)
```
