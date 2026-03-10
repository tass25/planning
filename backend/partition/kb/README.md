# `partition/kb/` — Knowledge Base Module

Knowledge Base management for verified SAS→Python/PySpark translation pairs.
Added in **Week 9** to support RAPTOR retrieval-augmented translation.

## Modules

| File | Purpose |
|------|---------|
| `kb_writer.py` | `KBWriter` — LanceDB table manager (insert, count, coverage stats, search) |
| `kb_changelog.py` | `log_kb_change()` / `get_history()` — DuckDB mutation audit trail |

## Architecture

```
┌───────────────────────┐
│  generate_kb_pairs.py │  (scripts/)
│  Dual-LLM chain:      │
│    A: Generate SAS     │─── Azure OpenAI GPT-4o
│    B: Convert→Python   │─── Azure OpenAI GPT-4o
│    C: Cross-verify     │─── Groq LLaMA-3.1-70B
└──────────┬────────────┘
           │ verified pairs (confidence ≥ 0.85)
           ▼
┌──────────────────────┐     ┌─────────────────────┐
│  KBWriter            │     │  kb_changelog        │
│  LanceDB table:      │     │  DuckDB table:       │
│  sas_python_examples │     │  kb_changelog        │
│  768-dim Nomic embed │     │  (insert/update/     │
│  IVF-64 cosine index │     │   rollback audit)    │
└──────────────────────┘     └─────────────────────┘
```

## KB Schema (16 fields)

| Field | Type | Description |
|-------|------|-------------|
| `example_id` | string | UUID primary key |
| `sas_code` | string | Original SAS code |
| `python_code` | string | Python/PySpark equivalent |
| `embedding` | float32[768] | Nomic Embed v1.5 vector |
| `partition_type` | string | SAS construct category |
| `complexity_tier` | string | LOW / MODERATE / HIGH |
| `target_runtime` | string | python / pyspark |
| `verified` | bool | Cross-verification passed |
| `source` | string | llm_gen / failure_mode_injection / manual |
| `failure_mode` | string | Targeted failure mode or empty |
| `verification_method` | string | llm_crosscheck / manual |
| `verification_score` | float32 | 0–1 confidence |
| `category` | string | 15 SAS categories |
| `version` | int32 | Version number |
| `superseded_by` | string | UUID of replacement or null |
| `created_at` | string | ISO 8601 timestamp |

## Coverage Targets

- **15 categories** × variable targets = ~250 base pairs
- **6 failure modes** × 10 targeted pairs = 60 extra pairs
- **Verification threshold**: confidence ≥ 0.85

## Related Scripts

| Script | Purpose |
|--------|---------|
| `scripts/generate_kb_pairs.py` | Full KB generation CLI |
| `scripts/kb_rollback.py` | Version rollback utility |
