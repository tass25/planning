# `backend/scripts/` — Operational & Research Scripts

Helper scripts for running the pipeline, managing the knowledge base,
evaluating quality, and running ablation studies. None of these are part of
the production server — they're CLI tools you run manually.

## Sub-directories

```
scripts/
├── kb/        — knowledge base generation, expansion, and rollback
├── eval/      — translation quality evaluation and benchmarking
├── ablation/  — RAPTOR vs flat-index ablation study
└── ops/       — pipeline CLI, deliverable verification
```

## `kb/`

| Script | What it does |
|--------|-------------|
| `generate_kb_pairs.py` | Generates SAS→Python pairs using a dual-LLM chain (generate → convert → cross-verify) and writes them to LanceDB |
| `expand_kb.py` | Batch-expand the KB by targeting categories with low coverage |
| `kb_rollback.py` | Roll back a KB entry to a previous version using the DuckDB changelog |
| `build_dataset.py` | Builds a fine-tuning dataset from gold standard + LanceDB + Gemini distillation |

## `eval/`

| Script | What it does |
|--------|-------------|
| `translate_test.py` | Runs the translation pipeline on a single file and prints results |
| `run_benchmark.py` | Runs the full gold-standard benchmark suite |
| `test_e2e_rag.py` | End-to-end test of the three RAG paradigms |

## `ablation/`

| Script | What it does |
|--------|-------------|
| `run_ablation_study.py` | Runs RAPTOR vs flat-index retrieval comparison |
| `init_ablation_db.py` | Initialises the DuckDB schema for ablation results |
| `analyze_ablation.py` | Reads ablation results and produces summary stats |

## `ops/`

| Script | What it does |
|--------|-------------|
| `run_pipeline.py` | CLI wrapper: `python run_pipeline.py path/to/file.sas` |
| `submit_correction.py` | Submits a human correction to the API (used for testing the correction flow) |
| `verify_deliverables.py` | Checks that all expected deliverables exist before submission |

## Running a script

All scripts assume you're inside the `backend/` directory and using the venv:

```bash
cd backend
C:/Users/labou/Desktop/Stage/venv/Scripts/python scripts/ops/run_pipeline.py path/to/file.sas
```
