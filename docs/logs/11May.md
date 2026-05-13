# 11 May 2026 — Session Log

## Supervisor Script Analysis + Embedding Fine-Tuning Integration

### Context
- Supervisor sent `Script_similarity_check.py` from EY's SAS-to-Python conversion accelerator
- The script implements a RAGConverter class using MongoDB + FAISS + `all-MiniLM-L6-v2` for similarity-based retrieval of SAS-to-Python pairs
- Key features: embedding fine-tuning (CosineSimilarityLoss), FAISS indexing, top-k accuracy evaluation
- Sent because the user reported LLM drift in translations regardless of prompt engineering

### Gap Analysis: Codara vs. Supervisor's Approach
1. **No embedding fine-tuning** — Codara uses vanilla Nomic (`nomic-embed-text-v1.5`) out-of-the-box; no domain adaptation
2. **No retrieval quality evaluation** — No metrics to measure whether RAG examples are actually relevant before feeding them to the LLM
- Codara already has LanceDB + hybrid retrieval (keyword + semantic), so MongoDB/FAISS migration is unnecessary

### Implementation — 4 Changes
1. **New: `backend/scripts/kb/fine_tune_embedder.py`** — Fine-tuning script for Nomic embedder using CosineSimilarityLoss on KB pairs from LanceDB. Generates contrastive training data automatically: same `partition_type` = positive (1.0), cross-modal SAS↔Python = positive (0.8), same broad category different type = medium (0.5), different category = negative (0.0)
2. **Edit: `backend/partition/raptor/embedder.py`** — Updated `NomicEmbedder` to auto-detect and load fine-tuned model from `backend/data/fine_tuned_embedder/` when `config.json` present, falls back to base Nomic otherwise
3. **Edit: `backend/partition/translation/kb_query.py`** — Added `MIN_SEMANTIC_SCORE = 0.45` threshold to reject results where the raw embedding similarity is too low (even if keyword score boosted them), with structured logging for rejected count
4. **New: `backend/scripts/eval/eval_retrieval.py`** — Retrieval evaluation script: leave-one-out strategy on KB entries, measures top-1/top-5 accuracy + MRR, supports `--compare` mode for base vs. fine-tuned side-by-side

### Files Changed
- `backend/scripts/kb/fine_tune_embedder.py` (new)
- `backend/scripts/eval/eval_retrieval.py` (new)
- `backend/partition/raptor/embedder.py` (modified — added `os` import, `FINE_TUNED_PATH`, auto-detection logic in `__init__`)
- `backend/partition/translation/kb_query.py` (modified — added `MIN_SEMANTIC_SCORE`, semantic floor filter before hybrid scoring)

### Commands to Run
```bash
# Fine-tune the embedder on KB pairs
cd backend && python scripts/kb/fine_tune_embedder.py --epochs 5 --batch 32

# Evaluate retrieval before/after
cd backend && python scripts/eval/eval_retrieval.py --compare

# Evaluate base model only
cd backend && python scripts/eval/eval_retrieval.py
```
