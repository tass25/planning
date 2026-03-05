# Week 12 — Done

**Completed**: Week 12
**Commit**: `dbaebf1` on `main`
**Tests**: 7 new (198 total passing, 2 pre-existing failures)

## Deliverables

### Evaluation — `partition/evaluation/`
| File | Description |
|------|-------------|
| `flat_index.py` | Extracts level-0 leaf nodes from RAPTOR → flat LanceDB table |
| `query_generator.py` | Stratified query generation (10/file, LOW/MOD/HIGH, 15 partition type templates) |
| `ablation_runner.py` | RAPTOR vs Flat comparison runner with DuckDB logging + summary computation |
| `README.md` | Module documentation |

### Scripts
| File | Description |
|------|-------------|
| `scripts/init_ablation_db.py` | Initialize ablation_results DuckDB schema |
| `scripts/analyze_ablation.py` | Analysis → console tables + Markdown report + PNG plots |

### Tests
| File | Tests |
|------|-------|
| `tests/test_evaluation.py` | 7 tests (query gen, flat index, ablation runner, schema init) |
| `tests/regression/test_ablation.py` | 3 regression guards (skipped if ablation.db absent) |

## Metrics Tracked
- RAPTOR hit-rate@5 (target > 0.82)
- MRR (target > 0.60)
- RAPTOR advantage on MODERATE/HIGH (target >= 10%)
- Query latency comparison
