# examples/

Runnable end-to-end examples for the SAS Converter L2 pipeline.

## demo_pipeline.py

Runs the **full deterministic pipeline** on a sample SAS file and prints:
- Every detected block (type, line range, risk level, LLM strategy)
- The full source code for each block
- A match summary against the expected gold annotation

```bash
cd sas_converter
$env:PYTHONPATH = "$PWD"
$env:LLM_PROVIDER = "none"          # skip Groq — deterministic only
$env:PYTHONIOENCODING = "utf-8"     # needed on Windows for Unicode output
../venv/Scripts/python examples/demo_pipeline.py
```

## test_input.sas

A 36-line SAS script containing the four canonical block types:

| Block | Lines | Type |
|-------|-------|------|
| `DATA sales` | 1–12 | `DATA_STEP` |
| `DATA sales_updated` | 14–19 | `DATA_STEP` |
| `PROC MEANS` | 21–28 | `PROC_BLOCK` |
| `PROC SQL` | 30–36 | `SQL_BLOCK` |

Expected pipeline output: **4/4 blocks, 100% accuracy**.
