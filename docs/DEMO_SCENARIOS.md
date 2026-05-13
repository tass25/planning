# Codara — Demo Scenarios

Three representative scenarios demonstrating Codara's capabilities, expected behavior, and known limitations.

---

## Scenario 1: Simple ETL (LOW risk, deterministic + StaticRAG)

**Input**: `gs_01_basic_data_step.sas` (7 lines, single DATA step)

```sas
data output;
  set input;
  revenue = price * quantity;
  if revenue > 1000 then flag = 'HIGH';
  else flag = 'LOW';
run;
```

**Expected behavior**:
- Pipeline stages: file_process (< 1s) → streaming (< 0.5s) → chunking (1 partition) → RAPTOR (skipped, < 2 partitions) → risk_routing (LOW) → persist → translation (StaticRAG, 3 KB examples) → merge
- Translation via primary LLM (Ollama minimax-m2.7:cloud or Azure GPT-5.4-mini)
- Z3 result: PROVED (linear arithmetic + conditional assignment patterns)

**Expected output**:
```python
import pandas as pd

output = input_df.copy()
output['revenue'] = output['price'] * output['quantity']
output['flag'] = output['revenue'].apply(lambda x: 'HIGH' if x > 1000 else 'LOW')
```

**Latency**: ~8-15s total (LLM dominates)
**Cost**: $0.00 (Ollama) or ~$0.001 (Azure GPT-5.4-mini)
**Known limitations**: None for this complexity level.

---

## Scenario 2: Medium Complexity (MOD risk, AgenticRAG + cross-verify)

**Input**: `gsm_01_financial_summary.sas` (~120 lines, PROC SQL + PROC MEANS + macro)

Key patterns: correlated subquery, BY-group processing, macro variable substitution, FORMAT application.

**Expected behavior**:
- Chunking produces 4-6 partitions (DATA step, PROC SQL, PROC MEANS, macro, global statements)
- RAPTOR builds 2-level tree (leaves + 1 cluster node)
- Risk routing: MODERATE for PROC SQL/macro, LOW for DATA steps
- Translation: AgenticRAG for MOD partitions (escalated k=8, graph traversal), StaticRAG for LOW
- Cross-verify: Groq independently translates, confidence compared (threshold 0.65)
- Failure mode detector flags: PROC_MEANS_OUTPUT, potentially DATE_ARITHMETIC

**Latency**: ~45-90s total (4-6 LLM calls × ~15s each)
**Cost**: $0.00 (Ollama) or ~$0.01-0.02 (Azure GPT-5.4-mini)
**Known limitations**:
- PROC FORMAT custom informats: translated to `pd.cut()` or dict mapping, may lose edge cases
- Macro %SYSFUNC: expanded but complex nested calls may produce incomplete expansion

---

## Scenario 3: Enterprise Hard (HIGH risk, multi-agent debate + Reflexion)

**Input**: `gsh_01_enterprise_etl.sas` (~400 lines, nested macros, hash objects, RETAIN, FIRST./LAST.)

Key patterns: %MACRO with %DO loops, hash object lookup, RETAIN with running totals, MERGE with multiple datasets, CALL EXECUTE.

**Expected behavior**:
- Chunking produces 8-12 partitions
- RAPTOR builds 3-level tree (leaf → cluster → root)
- Risk routing: HIGH for RETAIN/hash/macro, MODERATE for PROC SQL, LOW for globals
- Translation: Multi-agent debate for HIGH (Ollama + Azure in parallel, Groq judges)
- Reflexion retry triggered if cross-verify confidence < 0.65
- Failure modes flagged: RETAIN, FIRST_LAST, MERGE_SEMANTICS

**Latency**: ~2-4 min (debate doubles LLM calls, reflexion adds 1 retry)
**Cost**: $0.00 (Ollama) or ~$0.03-0.05 (Azure GPT-5.4-mini, 2x for debate)
**Known failure cases**:
- RETAIN with complex resets across BY-groups: translated to `groupby().transform()` but may miss reset-on-first logic
- Hash object with multiple keys + data: translated to dict or `pd.merge()`, hash iteration order may differ
- CALL EXECUTE: dynamic code generation — translated to `exec()` with safety warning, Z3 result is UNKNOWN
- Z3 scope: only 3-4 of 10 blocks fall in decidable fragment; rest are UNKNOWN (expected)

---

## Running the Demos

```bash
# Single file (Scenario 1)
cd backend && python scripts/ops/run_pipeline.py ../backend/knowledge_base/gold_standard/gs_01_basic_data_step.sas

# Full demo script (all 3 tiers)
cd backend && python examples/demo_pipeline.py

# Benchmark all models on torture test
cd backend && python scripts/eval/model_benchmark.py
```

---

## Failure Case Summary

| Failure Mode | Detection | Translation Impact | Mitigation |
|-------------|-----------|-------------------|------------|
| RETAIN | Regex (100%) | Prompt injection with `groupby().transform()` pattern | KB has 25+ RETAIN examples |
| FIRST./LAST. | Regex (100%) | Prompt injection with `shift()`/`ne()` pattern | KB has 20+ examples |
| DATE_ARITHMETIC | Regex (95%) | `pd.to_datetime()` + `pd.DateOffset` | SAS date epoch (1960-01-01) explicitly handled |
| MERGE_SEMANTICS | Regex (90%) | Left join default, merge indicators | SAS `IN=` variable semantics documented in prompt |
| MISSING_VALUE | Regex (100%) | `np.nan` comparisons with `.isna()` | SAS `.` < any number rule injected |
| PROC_MEANS_OUTPUT | Regex (85%) | `df.groupby().agg()` mapping | Output dataset name resolution can fail on multi-class |
| SORT_DIRECTION | Regex (100%) | `ascending=` parameter mapped | Rarely triggers |
| PROC_FORMAT | Regex (80%) | Dict mapping or `pd.cut()` | Custom informats are best-effort |
| COMPRESS_FUNCTION | Regex (90%) | `str.replace()` or regex | Multi-character compress handled |
| PROC_REG_STEPWISE | Regex (70%) | `statsmodels` OLS with manual stepwise | Automated stepwise is approximate |
