# Translation Layer (L3)

> **Agents**: TranslationAgent (#12), ValidationAgent (#13)  
> **Week**: 10  

## Overview

The translation layer converts SAS partitions to Python/PySpark code using
failure-mode-aware prompting, KB retrieval, and LLM-based translation with
post-translation validation via sandboxed execution.

## Architecture

```
PartitionIR (from L2-E)
  │
TranslationAgent (#12)
  ├─ 1. Failure-mode detection (6 rules)
  ├─ 2. KB retrieval (LanceDB k=5, filtered)
  ├─ 3. LLM routing: LOW → Azure GPT-4o-mini, MOD/HIGH → Azure GPT-4o
  ├─ 4. Translation prompt (few-shot from KB + failure-mode rules)
  └─ 5. Cross-verify (Groq LLaMA-70B, independent context)
  │
ValidationAgent (#13)
  ├─ 1. ast.parse() — syntax check
  ├─ 2. exec() sandbox on synthetic 100-row DataFrame (5s timeout)
  └─ 3. Routing: pass → L4, fail + retry < 2 → retranslate, else PARTIAL
  │
ConversionResult → L4 Merge
```

## Files

| File | Purpose |
|------|---------|
| `failure_mode_detector.py` | 6 regex-based SAS failure mode rules |
| `kb_query.py` | LanceDB retrieval with partition_type/failure_mode filters |
| `translation_agent.py` | TranslationAgent (#12), Azure OpenAI primary |
| `validation_agent.py` | ValidationAgent (#13), ast.parse + exec sandbox |
| `translation_pipeline.py` | translate → validate → retry loop + DuckDB logging |

## Failure Modes

| Mode | Pattern | Example |
|------|---------|---------|
| RETAIN | `RETAIN var` | Running totals across DATA step |
| FIRST_LAST | `FIRST.var` / `LAST.var` | BY-group boundary detection |
| DATE_ARITHMETIC | `INTNX`, `INTCK`, `MDY`, `TODAY()` | SAS date epoch (1960) |
| MERGE_SEMANTICS | `MERGE ... BY` | Sequential merge vs Cartesian join |
| MISSING_VALUE_COMPARISON | `NMISS`, `CMISS`, `. < x` | SAS missing = -∞ |
| PROC_MEANS_OUTPUT | `PROC MEANS ... OUTPUT OUT=` | Aggregate output dataset |

## LLM Routing (Azure-first)

| Risk Level | Primary | Fallback | Cross-verify |
|------------|---------|----------|--------------|
| LOW | Azure GPT-4o-mini | Groq LLaMA-70B | Groq LLaMA-70B |
| MODERATE/HIGH | Azure GPT-4o | Groq LLaMA-70B | Groq LLaMA-70B |

## Validation Sandbox

- **Syntax**: `ast.parse()` — catches all SyntaxError
- **Execution**: `exec()` on synthetic 100-row DataFrame with restricted builtins
- **Timeout**: 5s (threading-based, Windows-compatible)
- **Blocked**: `open`, `__import__`, `exec`, `eval`, `compile`, `exit`, `quit`
