# Evaluation — `partition/evaluation/`

RAPTOR vs Flat ablation study modules.

## Modules

| Module | Purpose |
|---|---|
| `flat_index.py` | Extracts level-0 (leaf) nodes from RAPTOR into a flat LanceDB table |
| `query_generator.py` | Generates stratified ablation queries (10 per file, LOW/MOD/HIGH) |
| `ablation_runner.py` | Executes RAPTOR vs Flat retrieval comparison, logs to DuckDB |

## Scripts

| Script | Purpose |
|---|---|
| `scripts/init_ablation_db.py` | Initialize ablation_results DuckDB schema |
| `scripts/analyze_ablation.py` | Analyze results → console tables + Markdown report + PNG plots |

## Regression Guards

| Test | Threshold |
|---|---|
| `test_raptor_hit_rate_overall` | hit-rate@5 > 0.82 |
| `test_raptor_advantage_moderate_high` | advantage >= 10% on MOD/HIGH |
| `test_ablation_query_count` | >= 1000 rows |

## Running the Study

```bash
python scripts/init_ablation_db.py
python scripts/analyze_ablation.py --db ablation.db --plots
pytest tests/regression/test_ablation.py -v
```
