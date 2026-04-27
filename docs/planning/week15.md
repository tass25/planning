# Week 15 — Plan

**Sprint**: Week 15 (Research Extension Sprint)
**Branch**: `main`
**Theme**: Neural fine-tuning, formal verification, hyperbolic clustering

---

## Objectives

| # | Objective | Layer | Priority |
|---|-----------|-------|----------|
| 1 | Build SAS→Python training corpus (1 000+ pairs) | Data | P0 |
| 2 | Fine-tune Qwen2.5-Coder-7B with QLoRA (SFT + DPO) | ML | P0 |
| 3 | Wire fine-tuned model into `llm_clients.py` as Tier 0 | L3 | P0 |
| 4 | Implement Z3 formal verification agent | L3 | P1 |
| 5 | Replace GMM clustering with HyperRAPTOR (Poincaré ball) | L2-C | P1 |
| 6 | Run ablation: fine-tuned vs GPT-4o vs Groq | Eval | P2 |
| 7 | Update benchmark & docs | All | P2 |

---

## 1. Data Collection — `scripts/build_dataset.py`

### Sources
| Source | Pairs (estimate) | Script |
|--------|-----------------|--------|
| Internal gold standard (existing) | 45 | already in `knowledge_base/gold_standard/` |
| KB pairs (existing) | 330 | already in LanceDB |
| The Stack v2 (HuggingFace) | ~400 | `scripts/build_dataset.py --source thestack` |
| GitHub API (SAS repos) | ~150 | `scripts/build_dataset.py --source github` |
| Teacher LLM distillation (GLM-4-Flash / Gemini) | ~200 | `scripts/distill_pairs.py` |
| Stack Overflow XML dump | ~75 | `scripts/build_dataset.py --source stackoverflow` |

### New Files
| File | Description |
|------|-------------|
| `scripts/build_dataset.py` | Orchestrates all scraping sources → unified JSONL |
| `scripts/distill_pairs.py` | Calls free teacher LLMs to translate raw SAS → Python |
| `scripts/dedup_dataset.py` | MinHash LSH deduplication (threshold 0.8) |
| `data/raw/` | Raw collected pairs (gitignored) |
| `data/sft_train.jsonl` | Final SFT-ready dataset |
| `data/dpo_train.jsonl` | DPO pairs (from `corrections` table) |

---

## 2. Fine-Tuning — QLoRA on Qwen2.5-Coder-7B

### SFT (Supervised Fine-Tuning)
- Base: `Qwen/Qwen2.5-Coder-7B-Instruct`
- Framework: `unsloth` + `trl` SFTTrainer
- Quantization: 4-bit QLoRA (LoRA r=16, alpha=32, target_modules=all-linear)
- Platform: Lightning AI free tier (2× A10G) or Google Colab T4
- Training: 3 epochs, batch=2, grad_accum=4, lr=2e-4, cosine scheduler
- Prompt format: Alpaca-style with SAS context header

### DPO (Direct Preference Optimization)
- Dataset: human corrections from `corrections` table (rejected=bad translation, chosen=human fix)
- Framework: `trl` DPOTrainer on top of SFT checkpoint
- β=0.1, learning_rate=5e-5

### Notebooks
| File | Purpose |
|------|---------|
| `notebooks/sft_qwen_qloraColab.ipynb` | SFT training notebook (Colab/Lightning) |
| `notebooks/dpo_qwen.ipynb` | DPO training notebook |

### Output
- Model saved to HuggingFace Hub: `{username}/codara-qwen2.5-coder-sas`
- GGUF quantized: `codara-qwen2.5-coder-sas-Q4_K_M.gguf` (for local inference via llama.cpp)

---

## 3. Local Model Client — `partition/utils/local_model_client.py`

New file: `LocalModelClient` wraps `llama_cpp.Llama` (or OpenAI-compatible vLLM endpoint).

Integration in `llm_clients.py`:
```
Tier 0 — LocalModelClient (fine-tuned, free, 7B, ~200ms)
Tier 1 — Azure OpenAI GPT-4o (primary cloud)
Tier 2 — Groq LLaMA-3.1-70B (fallback)
Tier 3 — PARTIAL status
```

New env var: `LOCAL_MODEL_PATH` — path to GGUF file or `http://localhost:8080` for vLLM.

---

## 4. Z3 Formal Verification Agent — `partition/verification/z3_agent.py`

### What it does
Uses Microsoft Z3 SMT solver to **formally prove** that a translated Python block is semantically equivalent to its SAS source.

### Scope (Week 15 subset — provable patterns)
| SAS Pattern | Z3 Encoding |
|-------------|-------------|
| Linear arithmetic (`sum`, `mean`, `count`) | Integer/Real arithmetic |
| Boolean filters (`WHERE`, `IF-THEN`) | Propositional logic |
| Sort/dedup invariants | Sequence ordering constraints |
| Simple macro expansion | Substitution lemmas |

### Pipeline integration
Inserted after `ValidationAgent`, before merge:
```
TranslationAgent → ValidationAgent → Z3VerificationAgent → merge
```
- PROVED → `verification_status = "formal_proof"`
- UNKNOWN → `verification_status = "unverifiable"` (non-blocking, fallback to heuristic)
- COUNTEREXAMPLE → flags block for human review (`risk_level → HIGH`)

### Files
| File | Description |
|------|-------------|
| `partition/verification/z3_agent.py` | `Z3VerificationAgent` — main SMT encoding |
| `partition/verification/sas_encoder.py` | SAS AST → Z3 formula translation |
| `partition/verification/py_encoder.py` | Python AST → Z3 formula translation |
| `partition/models/enums.py` | Added `VerificationStatus` enum |
| `tests/test_z3_verification.py` | Unit tests (arithmetic, boolean, sort) |

---

## 5. HyperRAPTOR — Poincaré Ball Clustering

### Motivation
SAS code has strong hierarchical structure (macro → PROC → DATA step). Euclidean GMM
loses this hierarchy. Hyperbolic space (Poincaré ball, curvature c=−1) preserves tree-like
structure: parent clusters stay near the origin, leaves on the boundary.

### Changes
| File | Change |
|------|--------|
| `partition/raptor/embedder.py` | Added `HyperbolicProjector` — maps Nomic 768-dim → Poincaré ball |
| `partition/raptor/clusterer.py` | Replaced `GMMClusterer` with `HyperRAPTORClusterer` (Poincaré K-means via `geoopt`) |
| `partition/raptor/raptor_agent.py` | Feature-flagged via `USE_HYPER_RAPTOR=true` env var |
| `requirements.txt` | Added `geoopt>=0.5.0` |

### Algorithm
1. Embed blocks with NomicEmbedder (unchanged, 768-dim)
2. Project to Poincaré ball: `x → tanh(‖x‖) · x/‖x‖`
3. Run Poincaré K-means (Riemannian gradient descent on `geoopt.manifolds.PoincareBall`)
4. Build RAPTOR tree on hyperbolic clusters

---

## 6. Ablation Study (updated)

Extended `ablation_runner.py` to include:

| Condition | Description |
|-----------|-------------|
| `flat_index` | Flat LanceDB KNN (baseline) |
| `raptor_euclidean` | RAPTOR + GMM (current Week 12) |
| `raptor_hyperbolic` | HyperRAPTOR + Poincaré K-means (new) |
| `finetune_7b` | Fine-tuned Qwen2.5-Coder + flat index |
| `finetune_7b_raptor` | Fine-tuned Qwen2.5-Coder + HyperRAPTOR |

Metrics: hit-rate@5, MRR, translation accuracy, latency, verification rate (Z3).

---

## New Dependencies

```
# requirements.txt additions
geoopt>=0.5.0          # Riemannian geometry for HyperRAPTOR
z3-solver>=4.13.0      # Formal verification
unsloth>=2024.11       # QLoRA fine-tuning (training only, not runtime)
trl>=0.12.0            # SFT + DPO trainers
datasets>=3.0.0        # HuggingFace datasets for corpus
datasketch>=1.6.0      # MinHash LSH deduplication
llama-cpp-python>=0.3  # Local model inference (optional, loaded lazily)
```

---

## Tests Target

| File | Tests |
|------|-------|
| `tests/test_z3_verification.py` | 12 new (arithmetic, boolean, sort, integration) |
| `tests/test_hyper_raptor.py` | 8 new (projection, clustering, tree build) |
| `tests/test_local_model_client.py` | 6 new (mock inference, fallback chain) |
| `tests/test_dataset_builder.py` | 5 new (dedup, format validation) |

**Target**: 278 + 31 = **309 tests, 0 errors**

---

## Success Criteria

| Metric | Target |
|--------|--------|
| Training corpus size | ≥ 1 000 pairs |
| Fine-tune perplexity (validation) | < 2.8 on SAS-python pairs |
| Z3 provability rate | ≥ 35% of LOW-risk blocks |
| HyperRAPTOR vs GMM (MRR) | ≥ +5% improvement |
| Translation accuracy (fine-tuned) | ≥ 85% on gold standard |
| All tests pass | 309 collected, 0 errors |
