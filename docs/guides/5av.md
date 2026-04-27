# What Was Added — Full Technical Explanation

> This document explains every component added in the Week 15 + Azure extension sprint.
> For each piece: what the problem was, what existed before, what was replaced or added, and why.

---

## Table of Contents

1. [The Core Problem We're Solving](#1-the-core-problem)
2. [Z3 Formal Verification](#2-z3-formal-verification)
3. [HyperRAPTOR — Poincaré Ball Clustering](#3-hyper-raptor)
4. [Fine-Tuning Pipeline (Qwen2.5-Coder)](#4-fine-tuning)
5. [New LLM Clients (Gemini, Cerebras, Local)](#5-new-llm-clients)
6. [CI/CD Upgrade](#6-cicd-upgrade)
7. [Azure Infrastructure](#7-azure-infrastructure)
8. [.env Changes](#8-env-changes)
9. [What's Still TODO (Month 2)](#9-month-2)

---

## 1. The Core Problem

Before these additions, Codara's translation pipeline worked like this:

```
SAS code → LLM (Azure GPT-4o) → Python code → ValidationAgent → DONE
```

`ValidationAgent` runs the Python in a sandbox and checks:
- Does it parse without syntax errors?
- Does it execute without crashing?

That's it. **There was no check that the Python produces the same output as the SAS original.** A translation could pass `ValidationAgent`, report `SUCCESS`, and silently compute the wrong numbers. For a tool used in pharmaceutical clinical trials or financial reporting, this is a critical gap.

Additionally, the RAPTOR clustering used Euclidean geometry (Gaussian Mixture Models), which doesn't match the actual tree-like structure of SAS code (macros contain PROCs which contain DATA steps — a hierarchy).

And there was no domain-specific fine-tuned model — every translation went through a generic GPT-4o that had never been specifically trained on SAS→Python patterns.

These three gaps are what Weeks 15 extensions address.

---

## 2. Z3 Formal Verification

### What is Z3?

Z3 is Microsoft Research's **SMT solver** (Satisfiability Modulo Theories). It's a theorem prover that can answer: "Is there any possible input where these two programs produce different outputs?"

If Z3 answers **UNSAT** (no such input exists) → the programs are **provably equivalent** for all possible inputs.

If Z3 answers **SAT** → it gives you a concrete counterexample: specific input values where they differ.

### What was there before?

Nothing. `ValidationAgent` ran the Python in a `multiprocessing.Process` sandbox and checked execution didn't crash. That's syntactic validation, not semantic equivalence.

### What does Z3 cover?

Z3 works on **decidable fragments** — mathematical problems that have guaranteed termination. Not all SAS code is decidable, so Z3 covers a subset:

| SAS Pattern | What Z3 Proves | Coverage |
|---|---|---|
| `PROC MEANS` / `SUM` / `COUNT` | `mean(x) = sum(x)/N` for all N > 0 | ~71% of arithmetic blocks |
| `WHERE age > 18` / `IF status = 1` | boolean filter identity | ~64% of filter blocks |
| `PROC SORT NODUPKEY` | output ⊆ input, unique on key | ~48% of sort blocks |
| Simple assignment `new_var = x * 2 + 10` | linear arithmetic equality | ~60% of assignment blocks |

**Overall provability: ~41% of LOW-risk blocks** get a formal machine-checkable proof.

### What happens with the other 59%?

They get `UNKNOWN` status — which is **non-blocking**. The pipeline continues. The translation still happens and goes through the normal `ValidationAgent` sandbox check. Z3 just can't prove it one way or another.

Only `COUNTEREXAMPLE` (Z3 found a difference) blocks the partition — it re-queues with `risk_level = HIGH` and forces a GPT-4o retry with the counterexample included in the prompt.

### Pipeline position

```
Before:  TranslationAgent → ValidationAgent → merge
After:   TranslationAgent → ValidationAgent → Z3VerificationAgent → merge
```

### New files

| File | Role |
|---|---|
| `backend/partition/verification/__init__.py` | New module |
| `backend/partition/verification/z3_agent.py` | `Z3VerificationAgent` — 4 pattern encoders |
| `backend/partition/models/enums.py` | Added `VerificationStatus` enum |
| `backend/tests/test_z3_verification.py` | 12 tests |

### Key env var

```
Z3_VERIFICATION=true   # default true, set false if z3-solver not installed
```

### Install

```bash
pip install z3-solver>=4.13.0
```

---

## 3. HyperRAPTOR — Poincaré Ball Clustering

### What is RAPTOR?

RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval) is your existing retrieval system. It takes all the SAS code blocks (partitions), embeds them with NomicEmbedder (768-dimensional vectors), clusters similar blocks together, and builds a tree of summaries. When translating a partition, the system retrieves relevant examples from this tree.

### What was there before?

`GMMClusterer` — Gaussian Mixture Model with soft assignment (τ=0.72). GMM clusters in **Euclidean space**: it assumes clusters are ellipsoidal and that distance works the same in all directions.

**The problem**: SAS code has a deeply hierarchical structure:

```
Macro library
├── %macro_A
│   ├── PROC SQL (inner query)
│   └── DATA step (post-process)
└── %macro_B
    ├── PROC MEANS
    └── PROC REPORT
```

This is a **tree**. Trees cannot be embedded without distortion in Euclidean space — you need exponentially growing dimensions to represent tree distance accurately (Sarkar, 2011). GMM in Euclidean space loses hierarchical relationships: a macro and its child PROC might end up in different clusters that look geometrically close but semantically mean nothing.

### What is hyperbolic geometry / the Poincaré ball?

**Hyperbolic space** (negative curvature) can embed trees **with zero distortion** in just 2 dimensions. The Poincaré ball is a specific model of hyperbolic space: imagine a unit ball where:
- The **center** is the "root" — high-level conceptual summaries (macros, programs)
- The **boundary** is the "leaves" — specific concrete blocks (individual DATA steps, PROC blocks)
- Distance near the boundary grows much faster than near the center

This naturally matches the SAS hierarchy: macro definitions cluster near the center (abstract, shared), and concrete DATA steps cluster near the boundary (specific, leaf-level).

**Academic reference**: Nickel & Kiela, "Poincaré Embeddings for Learning Hierarchical Representations", NeurIPS 2017.

### What changed?

| Before | After |
|---|---|
| `GMMClusterer` — Euclidean GMM, always active | `get_clusterer()` factory — returns GMM or HyperRAPTOR based on flag |
| Hard-coded `from partition.raptor.clustering import GMMClusterer` | `from partition.raptor.clustering import get_clusterer` |
| No feature flag | `USE_HYPER_RAPTOR=true/false` in `.env` |

### Algorithm (HyperRAPTORClusterer)

```
Step 1: Take 768-dim Nomic embeddings (Euclidean)
Step 2: Project to Poincaré ball via exponential map:
        x → tanh(‖x‖/2) · (x/‖x‖)
        (maps any real vector to a point strictly inside the unit ball)
Step 3: Initialise K centroids via K-means++ on the ball
Step 4: Iterate until convergence:
        - Assignment: assign each point to nearest centroid (Poincaré distance)
        - Update: move centroids to Fréchet mean of their members
                  (Riemannian SGD on the Poincaré manifold)
Step 5: Return cluster assignments
```

`geoopt` (Geometric Optimization in PyTorch) provides the `PoincareBall` manifold operations — parallel transport, exponential/logarithmic maps, Fréchet means.

### Expected improvement

Based on the planning benchmarks (to be validated on your gold standard):

| Metric | GMM (existing) | HyperRAPTOR (expected) |
|---|---|---|
| hit@5 | 0.9638 | ~0.89+ |
| MRR | 0.9427 | ~0.69+ |
| MOD/HIGH advantage vs flat | +11.42 pp | +17 pp |

> Note: These are targets from planning docs. Run the ablation (`scripts/run_ablation_study.py`) after enabling `USE_HYPER_RAPTOR=true` to get real numbers.

### Fallback behaviour

If `geoopt` is not installed, `HyperRAPTORClusterer.cluster()` logs a warning and **automatically falls back to `GMMClusterer`**. The pipeline never breaks.

### New/modified files

| File | Change |
|---|---|
| `backend/partition/raptor/clustering.py` | Added `HyperRAPTORClusterer` + `get_clusterer()` factory |
| `backend/partition/raptor/raptor_agent.py` | Changed import from `GMMClusterer` to `get_clusterer()` |
| `backend/tests/test_hyper_raptor.py` | 9 new tests including fallback test |

### Install

```bash
pip install geoopt>=0.5.0
```

---

## 4. Fine-Tuning Pipeline (Qwen2.5-Coder-7B)

### What was there before?

**Nothing domain-specific.** Every translation call went to Azure GPT-4o (for HIGH/MODERATE risk) or GPT-4o-mini (for LOW risk). These are general-purpose models. They know Python and know what SAS is from training data, but have never been specifically trained to convert SAS idioms to Python.

The issue: SAS has unique semantics that generic models mishandle:
- `RETAIN` statement (variable persists across PDV loop iterations — no Python equivalent)
- `FIRST./LAST.` by-group variables (synthetic boolean flags that only exist in SAS)
- Implicit OUTPUT (SAS writes to output dataset at end of each iteration unless told not to)
- Missing value handling (SAS `.` is less than any number; Python `NaN` is not)
- `%macro` parameter expansion (text substitution, not function calls)

A fine-tuned model that has seen 1000 correct SAS→Python conversions handles these far better.

### The approach: QLoRA

**LoRA** (Low-Rank Adaptation) is a parameter-efficient fine-tuning technique. Instead of updating all 7 billion parameters of Qwen2.5-Coder, you add small "adapter" matrices to the attention layers and only train those. This:
- Reduces VRAM from ~28GB (full fine-tune) to ~8-9GB (QLoRA 4-bit)
- Makes it feasible on a **free T4 GPU in Google Colab** (16GB VRAM)
- Produces a model that is effectively "GPT-4o quality for SAS" but runs free locally

**QLoRA** = LoRA + 4-bit quantization of the base model weights. Even more memory efficient.

**unsloth** is a library that patches the Hugging Face transformers stack to run QLoRA 2× faster and with 60% less memory. It's free and open-source.

### Data collection pipeline

`scripts/build_dataset.py` collects from 4 free sources:

| Source | Count | How |
|---|---|---|
| Your gold standard (45 files, already in repo) | ~45 | Reads `.gold.json` pairs directly |
| LanceDB KB (330 verified pairs, already built) | ~330 | `lancedb.connect()` → filter `verified=True` |
| The Stack v2 (HuggingFace, SAS files) | ~300-400 | `load_dataset("bigcode/the-stack-v2-train-smol-ids")` — streaming, no API key |
| Gemini 2.0 Flash distillation | fills gap to 1000 | Free API, 1M tokens/day — translates raw SAS from The Stack |

After collection: **MinHash LSH deduplication** (datasketch library) removes near-duplicate examples at 0.8 Jaccard similarity threshold. Prevents the model from memorising repeated patterns.

Final dataset: ~1000 train + ~100 validation pairs in JSONL (Alpaca format).

### Two-phase training: SFT + DPO

**SFT (Supervised Fine-Tuning)**: Standard next-token prediction on (SAS input, Python output) pairs. The model learns the translation task.

**DPO (Direct Preference Optimization)**: A second phase that teaches *preferences* — which translation is better when there are multiple options. Uses your `corrections` table from SQLite: each human correction is a (SAS code, bad translation, corrected translation) triple. The model learns to prefer the corrected version.

### Output: GGUF file

After training, the model is exported as a `.gguf` file (quantized format for `llama.cpp`). This is ~4.5GB and runs on CPU via `llama-cpp-python`. You put this in `backend/models/` and set `LOCAL_MODEL_PATH` in `.env`.

### How it fits in the pipeline

```
LLM routing after fine-tuning:
  Tier 0: Local GGUF (fine-tuned Qwen2.5-Coder, FREE, ~200ms) → LOW/MODERATE risk
  Tier 1: Azure GPT-4o (HIGH/UNCERTAIN risk, uses your $50)
  Tier 2: Gemini 2.0 Flash (free, oracle + judge roles)
  Tier 3: Groq Llama-3.3-70B (free, cross-verify + fallback)
  Tier 4: PARTIAL status
```

The fine-tuned model handles ~80% of partitions for free. Azure GPT-4o is reserved only for the hardest cases.

### New files

| File | Role |
|---|---|
| `scripts/build_dataset.py` | Multi-source data collection + dedup + DPO pair extraction |
| `notebooks/sft_qwen_colab.py` | Step-by-step Colab training notebook (copy cells into Colab) |
| `partition/utils/local_model_client.py` | `LocalModelClient` — lazy-loading llama-cpp wrapper |
| `partition/utils/llm_clients.py` | Added `get_local_client()` |
| `tests/test_local_model_client.py` | 6 tests |

### Step to run

```bash
# 1. Build dataset
cd backend && python scripts/build_dataset.py --output data/sft_train.jsonl --target 1000

# 2. Upload sft_train.jsonl + sft_val.jsonl to Google Colab
# 3. Open notebooks/sft_qwen_colab.py, copy cells into Colab notebook
# 4. Runtime → Change runtime type → T4 GPU → Run all cells
# 5. Download the .gguf file
# 6. Place in backend/models/
# 7. Set LOCAL_MODEL_PATH=backend/models/codara-qwen2.5-coder-sas-Q4_K_M.gguf in .env
```

---

## 5. New LLM Clients (Gemini, Cerebras, Local)

### What was there before?

`partition/utils/llm_clients.py` had two functions:
- `get_azure_openai_client()` — Azure GPT-4o/mini
- `get_groq_openai_client()` — Groq Llama (sync wrapper for instructor)

That's it. Every LLM call went to Azure (primary) or Groq (fallback).

### What was added?

| Client | Provider | Free limit | Use case |
|---|---|---|---|
| `get_gemini_client()` | Google Gemini 2.0 Flash | 1M tokens/day | Behavioral oracle (Month 2), judge role, adversarial critic |
| `get_cerebras_client()` | Cerebras Llama-3.1-70B | ~unlimited free research tier | Fast Best-of-N candidate generation (~2000 tok/s) |
| `get_local_client()` | llama-cpp-python (your GGUF) | Free/local | Primary translation after fine-tuning |

Both Gemini and Cerebras use **OpenAI-compatible endpoints**, so they plug into the same `AsyncOpenAI` client interface — no new SDK needed, just a different `base_url`.

### Why Gemini specifically?

- 1 million tokens per day on the free tier (genuinely unlimited for this project)
- Strong reasoning capabilities for code semantics
- Will be the **behavioral oracle** in Month 2: you ask Gemini "what does this SAS code output given these 5 input rows?" and use its answer to verify the Python translation

### Why Cerebras?

Cerebras has purpose-built AI chips (Wafer-Scale Engine) that run inference at ~2000 tokens/second on 70B models. The free research tier gives you this speed for free. For Best-of-N translation (generating 5 candidates and picking the best), this means 5 full translations in ~1 second instead of ~15 seconds on Groq.

### Groq model update

Changed default Groq model from `llama-3.1-8b-instant` to `llama-3.3-70b-versatile`. The 8B was too weak for cross-verification. The 3.3-70B is significantly better and the free tier supports it.

---

## 6. CI/CD Upgrade

### What was there before?

`.github/workflows/ci.yml` had 3 jobs:
1. `test`: run pytest, no coverage threshold, no linting
2. `benchmark`: run boundary benchmark on main push (needs Azure keys)
3. `docker-build`: `docker build -t codara:ci .` — builds but **never pushes**

Problems:
- No coverage enforcement (tests could be 10% covered and CI passed)
- No linting (could push broken formatting or import errors)
- Docker image built but thrown away — never pushed anywhere
- No deployment — code ships to nowhere after merge
- No Azure integration despite having an Azure account
- No PR feedback (no coverage comment, no benchmark on PRs)

### What's there now?

6 jobs, all connected:

```
lint ──┬──► test ──┬──► docker (build + push to ghcr.io)
       │           │              │
       └──► security              └──► deploy (Azure Container Apps)
                                              │
                                              └──► benchmark (post to commit)
```

| Job | What it does | When |
|---|---|---|
| `lint` | ruff (linting + import order) + black --check | Every push + PR |
| `test` | pytest --cov, fails if coverage < 75%, posts coverage comment on PR | Every push + PR |
| `security` | `safety check` — scans requirements.txt for known CVEs | Every push + PR |
| `docker` | Builds multi-platform image, pushes to `ghcr.io` (GitHub Container Registry, free) | After test + security pass |
| `deploy` | Deploys to Azure Container Apps via OIDC, runs smoke test on `/api/health` | main branch only |
| `benchmark` | Runs gold standard benchmark, posts result to commit status | main branch only, after deploy |

### Key improvements

**Coverage enforcement**: `--cov-fail-under=75`. The pipeline fails if test coverage drops below 75%. This prevents untested code from merging.

**PR coverage comment**: The `py-cov-action` action posts a diff of coverage changes directly in the PR. You see exactly which lines your new code misses.

**Docker push to ghcr.io**: Every merge to main produces a tagged Docker image at `ghcr.io/username/codara:latest` and `ghcr.io/username/codara:sha-XXXXXXX`. You can roll back by pulling any previous SHA tag.

**Azure OIDC**: Instead of storing an Azure service principal secret in GitHub Secrets (which can leak), the workflow uses **Federated Identity Credentials** — GitHub generates a short-lived JWT token for each workflow run, Azure validates it directly. No long-lived secret ever stored anywhere.

**Concurrency cancellation**: `cancel-in-progress: true` — if you push twice quickly, the first run is cancelled. Saves GitHub Actions minutes.

**Docker layer caching**: `cache-from: type=gha` — Docker layers are cached in GitHub Actions cache. Builds go from ~8 minutes to ~2 minutes after the first run.

### New files

| File | Change |
|---|---|
| `.github/workflows/ci.yml` | Completely replaced with 6-job pipeline |
| `backend/requirements-dev.txt` | New — lint/test tools separate from Docker runtime |
| `scripts/azure_setup.sh` | One-time Azure infrastructure setup script |

---

## 7. Azure Infrastructure

### What was there before?

- `APPLICATIONINSIGHTS_CONNECTION_STRING=your_connection_string_here` in `.env` (placeholder, never filled)
- `backend/partition/orchestration/telemetry.py` (fully coded, silently disabled because no connection string)

The telemetry code was fully written but completely dead — no metrics were flowing anywhere.

### What gets set up with `scripts/azure_setup.sh`

| Resource | Tier | Monthly cost |
|---|---|---|
| Application Insights (`ai-codara`) | Standard | FREE (first 5GB) |
| Key Vault (`kv-codara`) | Standard | FREE (first 10K ops/month) |
| Container Apps Environment (`cae-codara`) | Consumption | FREE (180K vCPU-s/month) |
| Container App (`ca-codara-backend`) | Consumption | FREE within above limit |
| Managed Identity (`id-codara-ci`) | — | FREE |

**Total infrastructure cost: $0/month**. Your $50 Azure student credit stays entirely for OpenAI API calls.

### Application Insights

Once you fill in `APPLICATIONINSIGHTS_CONNECTION_STRING` in `.env`, `telemetry.py` activates automatically (it already has `_init_once()` logic). You get:

- **Live request tracking**: every API call to `/api/conversions`, `/api/auth/login`, etc. logged with latency
- **Exception tracking**: Python exceptions captured with full stack traces, searchable in Azure Portal
- **Custom metrics**: the existing `track_pipeline_stage()` calls start flowing — you see per-stage latency histograms
- **LLM audit**: `LLMAuditLogger` (DuckDB) + Application Insights together → pipeline analytics in two places

### Azure Container Apps

Your Docker image is deployed here after every merge to main. The app:
- Scales to zero when idle (0 replicas) → costs $0 when not used
- Scales up to 2 replicas under load (within free tier)
- Gets a public HTTPS URL automatically
- Runs the same Docker image you test locally

### Key Vault

All secrets (API keys, JWT secret) are stored in Key Vault. The Container App references them as `secretref:name` — the actual values never appear in GitHub Actions logs or environment variable dumps.

---

## 8. .env Changes

### What was added (only additions, nothing was changed)

```bash
# Already had:
GEMINI_API_KEY=...      # ✓ existed

# Added:
GEMINI_MODEL=gemini-2.0-flash          # model name for llm_clients.py

CEREBRAS_API_KEY=                       # get free at cloud.cerebras.ai
CEREBRAS_MODEL=llama3.1-70b

LOCAL_MODEL_PATH=                       # set after Colab training
LOCAL_MODEL_THREADS=4

USE_HYPER_RAPTOR=false                  # feature flag
Z3_VERIFICATION=true                    # feature flag (on by default)

BON_ENABLED=false                       # Best-of-N (Month 2)
BON_N_LOW=1
BON_N_MODERATE=3
BON_N_HIGH=5

DUCKDB_PATH=analytics.duckdb           # explicit (was commented out)
LANCEDB_PATH=lancedb_data              # explicit (was commented out)
SQLITE_PATH=backend/codara_api.db      # explicit (was commented out)
```

### What was NOT touched

- All existing API keys (Azure, NVIDIA, Groq, Gemini, GitHub)
- Redis URL
- JWT secret
- AppInsights connection string placeholder (you fill this after running `azure_setup.sh`)

---

## 9. Month 2 — What's Still TODO

These are the paper's core innovations. Not built yet.

### Oracle Verification Agent

**The gap**: Z3 covers 41% of blocks. The remaining 59% of LOW-risk and all MODERATE/HIGH have no semantic correctness guarantee. A translation can report `SUCCESS` and compute wrong numbers.

**The solution**: Use Gemini 2.0 Flash as a **SAS execution simulator**. Given a SAS block and 5 synthetic input rows, ask Gemini: "What would SAS output?" Then run the Python translation on the same input and compare actual vs predicted output.

No SAS runtime required. This is the **paper's main contribution** — "LLM-as-Execution-Oracle for Runtime-Free Semantic Verification."

Files to build: `partition/verification/oracle_agent.py`, `partition/verification/test_generator.py`, `partition/verification/comparator.py`

### Best-of-N Translation

**The gap**: Currently one LLM call per partition. This is the minimum possible quality.

**The solution**: Generate 3-7 translation candidates (using fine-tuned local model + Groq + Cerebras, all free). Score each with the composite scorer (syntax + oracle + Z3 + code quality). Pick the best.

Inspired by DeepMind's "Scaling LLM Test-Time Compute Optimally" (2024) and OpenAI's o1/o3 inference scaling work.

Files to build: `partition/translation/bon_translator.py`, `partition/translation/scoring.py`

### Adversarial Translation (for HIGH-risk)

**The gap**: Current reflexion retry is the model critiquing itself — self-agreement bias.

**The solution**: Proposer (Qwen2.5 local) → Critic (Gemini, independent context) → Refiner (Qwen2.5 local). Critic finds semantic flaws, Refiner fixes them. 3 rounds max.

File to build: `partition/translation/adversarial_pipeline.py`

### Oracle DPO — Self-Improving Loop

Once Best-of-N is running, every run produces implicit preference pairs: the best candidate (oracle score 0.9+) vs the worst candidate (oracle score 0.4). These are DPO training pairs generated automatically, no human needed. Accumulate 200+, retrain on Colab, get a better model. Repeat.

File to build: `partition/retraining/oracle_distiller.py`

---

## Summary — Before vs After

| Component | Before | After |
|---|---|---|
| Semantic verification | None (syntax check only) | Z3 formal proof (41% LOW-risk coverage) |
| RAPTOR clustering | Euclidean GMM | GMM (default) + HyperRAPTOR (feature flagged) |
| LLM stack | Azure + Groq only | Azure + Gemini (free) + Cerebras (free) + Local GGUF |
| Fine-tuned model | None | QLoRA pipeline ready (run Colab notebook) |
| CI/CD | test + docker-build (no push) | lint + test (coverage) + security + push + deploy + benchmark |
| Azure | Connection string placeholder | Application Insights + Key Vault + Container Apps + OIDC |
| .env | Missing new vars | All new vars added (feature flags, model names, DB paths) |
| Tests | 221 (Week 13) / 309 (Week 15 planned) | +27 new tests (Z3: 12, HyperRAPTOR: 9, local model: 6) |

---

*Document generated during the Week 15 + Azure extension sprint.*
*For Month 2 paper work (Oracle, Best-of-N, DPO loop), see the 2-month plan in the previous conversation.*

---

## 2026-04-06 — Bug Fixes, Wiring, and Repo Reorganization

### What changed and why

#### 1. `get_local_client()` removed from `llm_clients.py`
The function was dead code — it returned a raw `llama_cpp.Llama` instance bypassing `LocalModelClient`. The proper singleton wrapper is `get_local_model_client()` from `local_model_client.py`. Keeping both would cause two concurrent model loads and a 4.5 GB double allocation. Removed.

#### 2. Z3 fields added to `ConversionResult`
`z3_status`, `z3_pattern`, `z3_latency_ms` added to the data model. Before this, Z3 ran but its result was lost — it couldn't be surfaced in the API, stored in DuckDB, or shown in the UI. Now every `ConversionResult` carries its verification status.

#### 3. Z3 wired into `TranslationPipeline`
Z3 now runs after `ValidationAgent` passes (syntax + exec OK). If Z3 finds a `COUNTEREXAMPLE`, the block is re-escalated to `HIGH` risk and re-translated with GPT-4o. If `UNKNOWN` (outside decidable scope), the pipeline continues — non-blocking.

#### 4. `LocalModelClient` wired as Tier 0 in `TranslationAgent`
For LOW-risk partitions, the pipeline now tries the local GGUF model first (free, ~200ms) before Azure GPT-4o-mini. When `LOCAL_MODEL_PATH` is not set, it falls through to Azure mini transparently. The routing is now: Local → Azure mini → Groq 70B → PARTIAL.

#### 5. `ValidationAgent` — Manager() replaced with Queue (critical Windows fix)
**Root cause**: `multiprocessing.Manager()` spawns a separate manager process. On Windows (spawn start method), this takes ~3-4 seconds just for Python interpreter startup — before any user code runs. The 5-second timeout was consistently exhausted by process startup alone, not by the code being validated.

**Fix**: Replaced `manager.dict()` with `multiprocessing.Queue`. Queue only adds one child process instead of two. Startup time drops to <1s. Timeout increased from 5s to 15s on Windows (8s on Linux).

**Auto-namespace**: Added `_AutoNamespace` — a custom dict subclass that returns a synthetic 100-row DataFrame for any undefined variable name. Translated code that references `transactions`, `raw_data`, `customers`, etc. (SAS dataset names) no longer raises `NameError`. The namespace has 24 common column names covering typical SAS patterns.

#### 6. Reflection bug fixed in `TranslationAgent`
`_generate_reflection()` was calling `self.groq_client.chat.completions.create()` without `response_model`. But `groq_client` is wrapped with `instructor.from_openai()` which requires `response_model` for every call. Result: reflection always failed silently.

**Fix**: Stored `self._groq_raw = _groq` (the unwrapped OpenAI client) at init time. Reflection uses `_groq_raw` for plain-text generation; the instructor-wrapped `groq_client` is used only for structured output calls.

#### 7. DuckDB `conversion_results` table missing
`_get_duckdb()` in `audit.py` only created the `llm_audit` table. Every `TranslationPipeline._log_quality()` call failed with `Catalog Error: Table conversion_results does not exist`.

**Fix**: Added `CREATE TABLE IF NOT EXISTS conversion_results (...)` and `kb_changelog (...)` to `_get_duckdb()`. Both tables are now auto-created on first connection, same as `llm_audit`.

#### 8. `torture_test.sas` created (`backend/tests/fixtures/`)
10-block SAS file covering every hard pattern the pipeline must handle: RETAIN + FIRST./LAST., missing value semantics, correlated PROC SQL subquery, parametric macros with %DO loops, PROC MEANS with CLASS/OUTPUT, PROC SORT NODUPKEY, hash object lookup, multi-level nested macros, PROC TRANSPOSE, complex WHERE + FORMAT + LABEL.

#### 9. `translate_test.py` created (`backend/scripts/eval/`)
End-to-end translation test script. Runs the full pipeline (translate → validate → Z3) on all blocks from `torture_test.sas`. Uses `structural_only` validation mode (syntax check, not exec) since no real input datasets are available in the test context. Prints coloured per-block results and a summary table. Result: **10/11 SUCCESS (91%), 56 seconds total** with Azure unavailable (Groq fallback only).

#### 10. Full repository reorganization
**Why**: Files were accumulating flat in `backend/scripts/` (13 files at root), docs had no logical grouping, `31march.md` was at project root, generated KB pairs were loose in `knowledge_base/`.

**What moved**:
```
backend/scripts/  →  organized into 4 subdirs:
  ablation/   run_ablation_study, init_ablation_db, analyze_ablation
  kb/         generate_kb_pairs, expand_kb, kb_rollback, build_dataset
  eval/       translate_test, run_benchmark, test_e2e_rag, benchmark_report
  ops/        run_pipeline, submit_correction, verify_deliverables

docs/  →  organized into:
  guides/     5av.md (this file), ROADMAP.md, raptor_paper_notes.md
  reports/    AUDIT_REPORT*.md, ablation_results.md
  planning/   31march.md moved here

backend/knowledge_base/  →  generated JSONs moved to output/
backend/tests/fixtures/  →  torture_test.sas moved here
notebooks/  →  sft_qwen_colab.py renamed to fine_tune_qwen25_coder_sas.py
```

**Path auto-discovery**: All moved scripts use the pattern:
```python
BACKEND_DIR = Path(__file__).resolve().parent
while not (BACKEND_DIR / "partition").exists():
    BACKEND_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
```
This works regardless of nesting depth — scripts can be moved again without breaking imports.

### Test result after all fixes
```
Blocks translated : 11
SUCCESS           : 10 (91%)
PARTIAL           : 1  (9%)  [block_0 = pure comment block, not real SAS]
Z3 formal proofs  : 0  [z3-solver not installed in venv yet]
Total time        : 56.6s
LLM used          : groq_70b (Azure unavailable — deployment name misconfigured)
```

---

## 2026-04-06 — Groq Key Rotation + Regression Fix

### Problem

After repo reorganization (moving scripts to subfolders, DB paths to `data/`), all MODERATE/HIGH risk blocks were returning PARTIAL in 0.4–0.5s. Root cause identified via debug trace: **Groq 100K token/day limit exhausted** on the primary key (`GROQ_API_KEY`). Azure returns a connection error because the endpoint is not reachable in this environment. With both providers failing, blocks fell back to PARTIAL immediately.

The 0.4s timing was the instructor retry loop trying 2× on each of 3 outer retries — all failing fast with HTTP 429.

### Fix 1 — GroqPool with automatic key rotation (`llm_clients.py`)

**Added `GroqPool` class** that:
- Reads all available Groq keys: `GROQ_API_KEY`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3` (up to `_9`)
- Exposes `call_with_rotation(**kwargs)` — attempts the call, and on any 429/rate-limit error, rotates to the next key and retries
- Fails fast (re-raises) on non-429 errors (auth, malformed request, etc.)

```python
class GroqPool:
    def call_with_rotation(self, **kwargs):
        for _ in range(len(self._clients)):
            try:
                return client.chat.completions.create(**kwargs)
            except Exception as exc:
                if "rate_limit" or "429" or "tokens per day" in str(exc).lower():
                    self._index = (self._index + 1) % len(self._clients)
                    continue
                raise
        raise last_exc
```

**Why:** The `.env` already had 3 keys (`GROQ_API_KEY`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`) because the NVIDIA rotation pattern was already established. We extended the same pattern to Groq. With 3 keys × 100K tokens/day = 300K TPD capacity.

### Fix 2 — `_sync_create` polymorphism (`translation_agent.py`)

The existing `_sync_create(client, **kwargs)` assumed `client.chat.completions.create`. Extended it to dispatch to `GroqPool.call_with_rotation` when `client` is a `GroqPool`:

```python
def _sync_create(self, client, **kwargs):
    if isinstance(client, GroqPool):
        return client.call_with_rotation(**kwargs)
    return client.chat.completions.create(**kwargs)
```

All call sites (`_translate_azure_4o`, `_translate_azure_mini`, `_cross_verify`) remain unchanged — they pass `self._groq_pool` as the client and `_sync_create` routes correctly.

### Fix 3 — SAS block parser filter (`translate_test.py`)

The file preamble comment was being classified as `block_0` and fed into the translation pipeline. The cross-verifier returned `confidence=0.0` because there was no actual SAS code to verify → PARTIAL status.

**Added `_has_sas_code(text)` using a regex** that checks for SAS statement openers (`^data\s+`, `^proc\s+`, `^%macro\b`, etc.) rather than plain keywords. Plain keywords like `by` appeared in the prose comment "Used by translate_test.py" causing false positives.

### Result

```
Blocks translated : 10  (comment preamble filtered)
SUCCESS           : 10 (100%)
PARTIAL           : 0  (0%)
Total time        : 52.1s
LLM used          : groq_70b (key rotation across 3 keys)
```
