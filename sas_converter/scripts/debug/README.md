# scripts/debug/

Scratch scripts produced during the L2-B / L2-C benchmarking cycles (weeks 2–4).

Each script targets a specific miss-category or regression in the boundary-detection benchmark.
They are **not production code** — they exist as historical artefacts so the investigation
steps can be reproduced or audited.

## Naming convention

| Prefix | Meaning |
|--------|---------|
| `v0_*` | Earlier iteration created at repo root before `sas_converter/` structure was finalised |
| `debug_gsh*` | Hard-tier gold file (`gsh_NN`) investigation |
| `debug_gsm*` | Medium-tier gold file (`gsm_NN`) investigation |
| `debug_miss*` | Cross-file miss-analysis across all tiers |
| `debug_fix_verify*` | Regression verification after a fix commit |
| `debug_cond*` | CONDITIONAL_BLOCK boundary failures |
| `debug_macro*` | MACRO_DEFINITION / MACRO_INVOCATION failures |
| `debug_trace*` | Step-by-step FSM tracing |

## output/

Redirect captures from debug runs (`python debug_*.py > output/...txt`).
These files are **gitignored on future runs** — only the original captures from
the benchmarking sessions are kept as reference.

## Running a debug script

```bash
cd sas_converter
$env:PYTHONPATH = "$PWD"
../venv/Scripts/python scripts/debug/debug_gsh04.py
```
