
---

## Session — Docker Hub Rebuild (friend's Azure deployment)

### .dockerignore cleanup
- Excluded `backend/knowledge_base/` (gold standard corpus, benchmark outputs, generated pairs — not needed at runtime; seed is in `seed_kb.py`)
- Excluded `backend/scripts/ablation/`, `backend/scripts/eval/` (research/evaluation scripts)
- Excluded individual KB generation scripts: `build_dataset.py`, `expand_kb.py`, `fine_tune_embedder.py`, `generate_kb_pairs.py`, `import_teammate_kb.py`, `ingest_custom_pairs.py`, `kb_rollback.py`
- Excluded `backend/benchmark/`, `backend/examples/`
- Excluded `notebooks/` (root-level)
- Kept `backend/scripts/kb/seed_kb.py` (called by `entrypoint.sh` on first boot)

### Frontend Dockerfile fixes
- Switched from `oven/bun:1-alpine` to `node:20-alpine` (bun had SSL cert verification failures: `UNABLE_TO_VERIFY_LEAF_SIGNATURE`)
- Added `npm config set strict-ssl false` before install (corporate SSL inspection)
- Removed `package-lock.json` from COPY (Windows-generated lockfile was missing `@rollup/rollup-linux-x64-musl` for Alpine Linux)
- **Files**: `frontend/Dockerfile`

### Images pushed to Docker Hub
- `tesnimeellabou/codara-backend:latest` — 4.99 GB
- `tesnimeellabou/codara-frontend:latest` — 94.5 MB
