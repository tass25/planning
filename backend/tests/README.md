# backend/tests — Test Suite

## Purpose
Unit and integration tests for all pipeline layers.
22 test modules, ~248 assertions (as of Week 15).

## Running

```bash
# From the Stage/ root
cd backend
C:/Users/labou/Desktop/Stage/venv/Scripts/python -m pytest tests/ -v --tb=short

# With coverage
C:/Users/labou/Desktop/Stage/venv/Scripts/python -m pytest tests/ --cov=partition --cov-report=term-missing
```

## Structure

| File | What it covers |
|------|---------------|
| `test_streaming.py`       | StreamAgent, StateAgent, backpressure, perf |
| `test_boundary_detector.py` | BoundaryDetector + LLMBoundaryResolver |
| `test_complexity_agent.py` | ComplexityAgent ML calibration |
| `test_strategy_agent.py`  | StrategyAgent routing decisions |
| `test_rag.py`             | RAGRouter + Static/Graph/Agentic RAG |
| `test_raptor.py`          | RAPTOR tree building, GMM clustering |
| `test_translation.py`     | TranslationAgent, cross-verify, reflexion |
| `test_orchestration.py`   | Full pipeline integration |
| `test_persistence.py`     | SQLite persistence layer |
| `test_evaluation.py`      | Flat index + ablation queries |
| `test_merge_retraining.py`| MergeAgent + KB feedback loop |
| `test_file_analysis.py`   | FileAnalysisAgent |
| `test_cross_file_deps.py` | CrossFileDepsResolver |
| `test_data_lineage.py`    | DataLineageExtractor |
| `test_registry_writer.py` | RegistryWriterAgent |
| `test_robustness_kb.py`   | KB rollback/versioning |
| `test_integration.py`     | End-to-end API tests |
| `test_z3_effect.py`       | Z3 SMT verification patterns |
| `regression/test_ablation.py` | RAPTOR vs flat index ablation |

## Fixtures
`fixtures/torture_test.sas` — 10-block SAS file covering RETAIN, FIRST./LAST.,
correlated SQL, macros, hash, PROC MEANS, TRANSPOSE.

## Notes
- Tests that require a running LLM (Azure/Groq) are skipped when keys are absent.
- Test 8 in `test_streaming.py` uses a hardcoded Windows path — skipped if file missing.
