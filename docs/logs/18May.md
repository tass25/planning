# 18 May 2026 — Session Log

## Paper Revision:  Feedback (CDAIS_MIS_paper.tex)

### ALL 5  POINTS — STATUS

| # | Point | Status | Details |
|---|-------|--------|---------|
| 1 | MIS "Synthesis" → "Selection" | DONE | Renamed throughout paper |
| 2 | VTP 12→30-40 pairs + LOO-CV | DONE | 142 pairs (12+130 enterprise), LOO-CV implemented and run |
| 3 | Fix SORT_STABLE (C3) | DONE | 17-row override, 6/6 detection |
| 4 | SORT_STABLE in abstract | DONE | Now reports 6/6 with override mention |
| 5 | Impact (no action needed) | N/A | Already a strength per supervisor |

### Point 1 — MIS terminology

- Renamed MIS from "Migration Invariant Synthesis" to "Migration Invariant Selection" throughout paper
- Abstract, §5, contributions, conclusion, related work, limitations all updated
- Added terminology note in §5.1 clarifying selection vs synthesis

### Point 3 — SORT_STABLE (C3) fix

- Empirically found numpy introsort threshold: n=17 (verified 100/100 deterministic, numpy 1.26 + pandas 2.3)
- Modified `constraint_catalog.py`: 17-row witness with strict ordering s_0 < s_1 < ... < s_16
- Modified `synthesizer.py`: model extraction for new encoding
- First attempt with z3.Distinct timed out; replaced with ordered chain — trivially solvable
- **eval_cdais_direct.py results:**
  - CDAIS detection: **6/6 = 100.0%** (was 5/6)
  - SORT_STABLE: 17-row witness, 296ms, DIVERGES confirmed
  - SORT_STABLE random PTDR: 25.5%, heuristic PTDR: 46.0%
  - RETAIN_RESET: 72.5%/100%, LAG_QUEUE: 78.5%/100%, NULL_ARITHMETIC: 100%/100%, JOIN_TYPE: 100%/100%, GROUP_BOUNDARY: 75.0%/100%
  - Avg synthesis: 73ms, avg witness size: 8 rows

### Point 2b — LOO cross-validation for MIS

- Added `LOOCVResult`, `LOOCVReport` dataclasses to `invariant_synthesizer.py`
- Added `leave_one_out_cv()` method to `MigrationInvariantSynthesizer`
- Updated `run_mis.py`: added `--loo-cv` flag

### Point 2a — VTP expansion to 142 pairs

- Integrated `result 1.json` (130 enterprise SAS→Python pairs from senior SAS developer)
- Copied to `knowledge_base/output/verified_senior_manager_pairs.json`
- Updated `run_mis.py` `_load_benchmark_pairs()` to load `verified_*_pairs.json` files
- **MIS results on 142-pair corpus:**
  - 142 pairs loaded, 142 observations
  - **10 confirmed / 8 rejected** (same count, DIFFERENT composition vs 12 pairs)
  - Invariants that CHANGED status (12→142 pairs):
    - DEMOTED (confirmed→rejected): COLUMN_SUPERSET (96.6%), ROW_PRESERVATION_NON_FILTER (92.9%), ROW_EQUALITY_SORT (58.3%)
    - PROMOTED (inapplicable→confirmed): FIRST_LAST_SUBSET (3 app, 100%), FREQ_PERCENT_SUM_100 (2 app, 100%), ROW_REDUCTION_DEDUP (5 app, 100%)
  - MIS latency: 937ms
- **LOO-CV on 142 pairs:**
  - 142 folds, all 18 invariants: **0 fragile**
  - 10 confirmed: 142/142 stable each
  - 8 rejected: 0/142 stable each
  - LOO-CV latency: 12.1s

### Paper tables/sections updated

- Abstract: 6/6 CDAIS, 142-pair VTP, LOO-CV zero fragile
- Table 2 (datasets): VTP 142 pairs (12 + 130 enterprise)
- VTP description paragraph: rewritten for 142-pair combined corpus
- Table 6 (MIS results): completely rewritten with 142-pair data
- MIS analysis paragraph: discusses 3 demoted + 3 promoted invariants
- LOO-CV paragraph: 142/142 folds, zero fragile
- Corpus size effect paragraph: validates supervisor's prediction
- Contributions (item 3): 142-pair corpus, LOO-CV
- Conclusion: 142-pair, composition changed, LOO-CV stable
- Limitations: updated for 142 pairs (only 1 inapplicable invariant now)
- Future work: removed VTP expansion (done), added automated candidate generation

### Files modified

- `docs/research/CDAIS_MIS_paper.tex` — all paper edits
- `backend/partition/testing/cdais/constraint_catalog.py` — SORT_STABLE 17-row encoding
- `backend/partition/testing/cdais/synthesizer.py` — SORT_STABLE model extraction
- `backend/partition/invariant/invariant_synthesizer.py` — LOOCVResult, LOOCVReport, leave_one_out_cv()
- `backend/scripts/eval/run_mis.py` — --loo-cv flag + verified_*_pairs.json loader
- `backend/knowledge_base/output/verified_senior_manager_pairs.json` — 130 enterprise pairs
- `backend/output/cdais_eval_direct.json` — updated eval results

### Supervisor follow-up — two refinement points

**Theorem 1 proof expanded** (was "Proof sketch", now full proof):
- 3-step contrapositive structure: (1) witness satisfies divergence constraints, (2) bug implies divergence on W, (3) contrapositive conclusion
- References concrete encoding design (e.g. RETAIN_RESET equations)
- No longer labelled "sketch"

**Corpus annotation limitation added:**
- New paragraph in §7.1 acknowledging single-annotator validation for the 130 enterprise pairs
- Notes absence of Cohen's κ / double annotation
- Suggests future work: double annotation on 30-50 pair subset with measured κ

### Figure 4 caption updated
- Changed "200 trials" → "1000 trials" to match actual random testing data
- Figure numbering verified: Fig1=taxonomy, Fig2=CDAIS workflow, Fig3=pipeline, Fig4=detection rates — all consistent via `\ref{}`
