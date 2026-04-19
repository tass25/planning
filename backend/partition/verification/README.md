# `partition/verification/` — Formal Verification (Z3)

Added in **Week 15** as an optional post-translation correctness check using
Microsoft's Z3 SMT solver.

## Files

| File | Purpose |
|------|---------|
| `z3_agent.py` | `Z3VerificationAgent` — encodes SAS+Python semantics into SMT formulas and checks equivalence |

## How it works

Z3 can't run arbitrary code, so the agent extracts the *semantic skeleton* of
both the SAS block and the Python translation and encodes it as a set of
logical constraints. If Z3 finds a counter-example (an input where the two
programs produce different outputs), the translation is flagged for repair.

### Supported patterns (4 SMT encoders)

| Pattern | What it checks |
|---------|---------------|
| Linear arithmetic | `+`, `-`, `*`, `/`, comparisons — checks numeric equivalence |
| Boolean filter | `WHERE`/`IF` conditions — checks that filter logic is preserved |
| Sort / dedup | `PROC SORT NODUPKEY` → `drop_duplicates` — checks ordering and uniqueness |
| Assignment | Simple `data step` variable assignments → Python variable binding |

### What Z3 can't cover

Z3 is sound but incomplete here — it only checks the patterns above. Complex
SAS constructs (hash lookups, macro expansion, PROC SQL with subqueries) fall
back to the ValidationAgent sandbox instead.

## Feature flag

Controlled by `settings.enable_z3_verification` (default: `True`).
Set `ENABLE_Z3_VERIFICATION=false` to skip Z3 and rely on sandbox-only validation.

## Dependencies

`z3-solver` — must be installed separately: `pip install z3-solver`
