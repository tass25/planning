# Translation Layer (L3)

> **Agents**: TranslationAgent (#12), ValidationAgent (#13)
> **Week**: 10 (updated week 15+ for Nemotron routing)

## Overview

The translation layer converts SAS partitions to Python using failure-mode-aware
prompting, knowledge-base retrieval, and a three-tier LLM fallback chain with
post-translation validation via sandboxed execution.

## Architecture

```
PartitionIR (from L2-E)
  │
TranslationAgent (#12)
  ├─ 1. Failure-mode detection (6 rules)
  ├─ 2. KB retrieval (LanceDB k=5, filtered by partition_type / failure_mode)
  ├─ 3. LLM routing: Tier 1 → Tier 2 → Tier 3 (see table below)
  ├─ 4. Translation prompt (few-shot from KB + failure-mode hints)
  └─ 5. Cross-verify (Prompt C): independent second model checks equivalence
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
| `kb_query.py` | LanceDB semantic retrieval with partition_type / failure_mode filters |
| `translation_agent.py` | TranslationAgent (#12) — LLM routing + RAG + cross-verify |
| `validation_agent.py` | ValidationAgent (#13) — ast.parse + exec sandbox |
| `translation_pipeline.py` | translate → validate → retry loop + DuckDB audit logging |
| `deterministic_translator.py` | Rule-based fast path for trivial patterns (no LLM call) |
| `macro_expander.py` | Inlines SAS %macro definitions before translation |
| `format_mapper.py` | Converts SAS format names to Python equivalents in the prompt |
| `sas_builtins.py` | Documents SAS built-in functions for the LLM prompt |
| `sas_type_inferencer.py` | Infers column types from DATA step context |
| `kb_query.py` | LanceDB k-NN retrieval, filtered by partition type and failure mode |

## Failure Modes

Six patterns that catch SAS → Python pitfalls before the LLM sees the code.
Each detected mode adds targeted rules to the translation prompt.

| Mode | Pattern | Why it matters |
|------|---------|----------------|
| RETAIN | `RETAIN var` | Running totals reset between rows in pandas unless you shift |
| FIRST_LAST | `FIRST.var` / `LAST.var` | BY-group boundaries need `groupby` + `cumcount` tricks |
| DATE_ARITHMETIC | `INTNX`, `INTCK`, `MDY`, `TODAY()` | SAS dates count days since 1960-01-01, not 1970 |
| MERGE_SEMANTICS | `MERGE ... BY` | SAS merge is sequential (not Cartesian) — maps to `pd.merge(..., how='outer')` |
| MISSING_VALUE_COMPARISON | `NMISS`, `CMISS`, `. < x` | SAS treats `.` (numeric missing) as negative infinity in comparisons |
| PROC_MEANS_OUTPUT | `PROC MEANS ... OUTPUT OUT=` | Aggregate output is a new dataset, not a printed report |

## LLM Routing (Nemotron-first since week 15)

| Tier | Provider | Model | When used |
|------|----------|-------|-----------|
| 1 (primary) | Ollama | `nemotron-3-super:cloud` | Every request first |
| 2 (fallback 1) | Azure OpenAI | GPT-4o / GPT-4o-mini | Tier 1 unavailable or circuit open |
| 3 (fallback 2 + cross-verifier) | Groq | LLaMA-3.3-70B | Tier 2 unavailable or for cross-verify |
| 4 (terminal) | — | — | All tiers exhausted → PARTIAL status |

Cross-verification uses Groq independently (separate context window) so the
verifier can't be fooled by the same mistake the primary model made.

## Validation Sandbox

- **Syntax**: `ast.parse()` — catches SyntaxError before execution
- **Execution**: `exec()` in a subprocess with a synthetic 100-row DataFrame
- **Timeout**: 5 seconds via `multiprocessing.Process.kill()` (true isolation, Windows-safe)
- **Blocked builtins**: `open`, `__import__`, `exec`, `eval`, `compile`, `exit`, `quit`
- **Retry**: up to 2 re-translations before marking the partition PARTIAL
