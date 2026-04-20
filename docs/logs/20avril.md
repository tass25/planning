# Session Log — 20 April 2026

---

## VS Code git warning fix

- **Problem**: VS Code logged `[warning] [Git][revParse] Unable to read file: ENOENT ... refs/remotes/origin/main` every 5 seconds
- **Root cause**: git stores the remote ref in `.git/packed-refs` (normal after fetch/pack); VS Code tries to read it as a loose file and fails
- **Fix**: manually wrote the SHA from `packed-refs` into `.git/refs/remotes/origin/main` as a loose file
- Warning stopped immediately, no git behavior changed

---

## .env restored

- `.env` was gitignored and not committed — disappeared during repo cleanup
- Recovered from Planning branch: `git show Planning:.env > .env`
- Changed `OLLAMA_MODEL=minimax-m2.7:cloud` → `nemotron-3-super:cloud` in `.env`

---

## LLM chain order fixed

**Previous chain (wrong):** Nemotron (Ollama) → Azure → Groq  
**Corrected chain:** Azure GPT-4o → Nemotron (Ollama) → Groq

Files changed:
- `backend/partition/translation/translation_agent.py` — swapped Tier 1/2 in `_call_llm()`, cross-verify, debate gather, all docstrings and labels
- `backend/partition/utils/llm_clients.py` — fixed module docstring
- `infra/azure_setup.sh` — `OLLAMA_MODEL=nemotron-3-super:cloud` in Container App env vars

---

## Python 3.10 compatibility fix

`asyncio.timeout()` (context manager) was introduced in Python 3.11. Venv is Python 3.10.

Files fixed:
- `backend/partition/translation/translation_pipeline.py` — replaced `async with asyncio.timeout(...)` with `asyncio.wait_for(..., timeout=...)`
- `backend/api/main.py` — same fix in all 4 health-check helpers (`_check_sqlite`, `_check_redis`, `_check_lancedb`, `_check_ollama`)

---

## Azure infra: Key Vault → Container Apps wiring fixed

**Problem**: `azure_setup.sh` stored secrets in Key Vault but never granted the managed identity access to read them. CI deploy used `secretref:` (Container Apps secret store) but those secrets were never populated from Key Vault.

**Fix** (`infra/azure_setup.sh`):
- Added `az role assignment create --role "Key Vault Secrets User"` for the managed identity on the Key Vault
- Container App now created with `--secrets keyvaultref:...` syntax pointing to Key Vault URIs
- Prompts for `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`, `FRONTEND_URL` (for CORS) — previously missing
- `CORS_ORIGINS` and `OLLAMA_MODEL=nemotron-3-super:cloud` added to Container App env vars

**Fix** (`.github/workflows/ci.yml`):
- Deploy step changed from `az containerapp up` (resets all secrets on each deploy) to `az containerapp update --image` (image-only update, secrets untouched)

---

## Torture test re-run

Command:
```bash
PYTHONPATH=backend python backend/scripts/eval/translate_test.py backend/tests/fixtures/torture_test.sas
```

Results with Nemotron as fallback (Azure connection failed locally, circuit breaker tripped after 5 failures):

| Block | Result | Model | Conf | Z3 |
|-------|--------|-------|------|----|
| 1. RETAIN + BY-group FIRST./LAST. | SUCCESS | ollama_nemotron-3-super:cloud | 0.80 | z3_unknown |
| 2. Missing value logic | SUCCESS | ollama_nemotron-3-super:cloud | 0.95 | unverifiable |
| 3. PROC SQL correlated subquery | SUCCESS | ollama_nemotron-3-super:cloud | 0.95 | unverifiable |
| 4. Macro + %DO loop | SUCCESS | ollama_nemotron-3-super:cloud | 0.95 | unverifiable |
| 5. PROC MEANS CLASS OUTPUT | SUCCESS | ollama_nemotron-3-super:cloud | 0.95 | formal_proof |
| 6. PROC SORT NODUPKEY | SUCCESS | deterministic | 1.00 | formal_proof |
| 7. Hash object lookup | SUCCESS | ollama_nemotron-3-super:cloud | 0.95 | unverifiable |
| 8. Multi-level nested macro | SUCCESS | ollama_nemotron-3-super:cloud | 0.95 | unverifiable |
| 9. PROC TRANSPOSE | SUCCESS | ollama_nemotron-3-super:cloud | 0.95 | — |
| 10. Complex WHERE + FORMAT | SUCCESS | ollama_nemotron-3-super:cloud | 0.90 | formal_proof |

**10/10 SUCCESS (100%)** — 3 Z3 formal proofs, 0 counterexamples, total time 104.2s  
Output saved to `backend/output/translate_test/`

---

## SemantiCheck — novel verification framework (NEW)

**Motivation**: CodeBLEU compares text; two semantically identical translations can score low if styled differently. Confidence scores come from the LLM that produced the translation (self-reported, biased). Z3 only covers ~30% of SAS patterns.

**SemantiCheck Score (SCS)** = weighted composite of 4 independent layers:

| Layer | Name | Method | Weight |
|-------|------|--------|--------|
| L1 | Formal | Z3 SMT proof (existing) | 30% |
| L2 | Behavioral | CDAIS witness execution (existing) | 30% |
| L3 | Contract | Semantic Transformation Graph (STG) comparison — NEW | 20% |
| L4 | Oracle | LLM simulates SAS execution, compare with Python output — NEW | 20% |

**L3 — Contract (novel):**
- Extracts a language-agnostic STG from SAS (regex + heuristics) and from Python (AST walk)
- STG nodes: READ, FILTER, SORT, GROUP, AGGREGATE, COMPUTE, MERGE, DEDUP, TRANSPOSE, WRITE
- Compares sets of operation types using Jaccard similarity
- Syntax-independent: two different implementations of the same logic score identically

**L4 — Oracle (novel):**
- Synthesizes a representative 3-row input DataFrame from column names found in the SAS source
- Asks LLM to predict SAS output (columns, row count direction, transformations)
- Asks same LLM to predict Python output on the same input (independent prompt)
- Scores agreement on: column set (50%), row count change (30%), transformation keywords (20%)
- First tool to use LLM-as-SAS-oracle for behavioral testing without a SAS license

**Verdicts:** VERIFIED (SCS ≥ 0.85) / LIKELY_CORRECT (≥ 0.65) / UNCERTAIN (≥ 0.40) / LIKELY_INCORRECT (< 0.40)

**Torture test SemantiCheck results** (Nemotron oracle, L3+L4 only — L1/L2 not wired into standalone script yet):

| Block | SCS | Verdict | L3 | L4 |
|-------|-----|---------|----|----|
| RETAIN + BY-group | 0.900 | VERIFIED | 1.00 | 0.80 |
| Missing value logic | 0.460 | UNCERTAIN | 0.33 | 0.59 |
| PROC SQL subquery | 0.400 | UNCERTAIN | 0.00 | 0.80 |
| Macro + %DO loop | 0.275 | LIKELY_INCORRECT | 0.00 | 0.55 |
| PROC MEANS | 0.683 | LIKELY_CORRECT | 0.50 | 0.87 |
| PROC SORT NODUPKEY | 0.925 | VERIFIED | 1.00 | 0.85 |
| Hash object lookup | 0.783 | LIKELY_CORRECT | 1.00 | 0.57 |
| Multi-level macro | 0.275 | LIKELY_INCORRECT | 0.25 | 0.30 |
| PROC TRANSPOSE | 0.150 | LIKELY_INCORRECT | 0.00 | 0.30 |
| Complex WHERE | 0.666 | LIKELY_CORRECT | 1.00 | 0.33 |

**Avg SCS: 0.552 | 5/10 VERIFIED or LIKELY_CORRECT | Avg L3: 0.508 | Avg L4: 0.595**

Key finding: PROC TRANSPOSE and macros score `LIKELY_INCORRECT` — the Python runs but doesn't preserve the structural intent. CodeBLEU would not catch this.

New files:
- `backend/partition/verification/semanticheck.py` — full SemantiCheck engine
- `backend/scripts/eval/run_semanticheck.py` — standalone evaluation script

Report saved to: `backend/output/translate_test/semanticheck_report.json`

---

## Commits this session

| Hash | Message |
|------|---------|
| `0049ba2d` | infra: wire Key Vault → Container Apps via managed identity, simplify CI deploy |
| `d72e64f8` | fix: swap LLM chain to Azure primary → Nemotron fallback → Groq, fix Python 3.10 compat |
| `831dd662` | feat: SemantiCheck — novel 4-layer semantic verification framework |

---

## Pending

- `git push origin main` — SSH kept dropping (connection abort to 140.82.121.x); commits are local, push when connection is stable
- SemantiCheck L1/L2 integration into the main pipeline (currently standalone eval script only)
- Frontend deployment (Azure Static Web Apps or second Container App)
- `azure_setup.sh` still needs to be run once to provision Azure infra
