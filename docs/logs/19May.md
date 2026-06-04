# 19 May 2026 — Session Log

## Report Updates: Reflect 18May Paper Changes

### Changes Applied to Report

Propagated all CDAIS/MIS paper changes (from 18May session) into the PFE report across 7 files:

#### abstract.tex
- Updated verification frameworks: "three" → "four" (added MIS)
- Added CDAIS concrete results: "deterministic 1-trial detection for all 6 of 6 error classes, 6-17 row witnesses, ~73ms synthesis"
- Added MIS: "confirming 10 of 18 invariants on 142-pair corpus with LOO-CV stability"
- Added "migration invariants" to keywords

#### chapter0_intro.tex
- Added MIS framework to system description alongside CDAIS and SemantiCheck

#### chapter1.tex
- Updated v3.1.0 description: added MIS (10/18 invariants, 142-pair corpus) and CDAIS (6/6 detection with coverage certificates)

#### chapter5.tex (Implementation)
- Added new subsection §5.11.1: Formal Error Class Taxonomy — table of 6 classes (C1-C6)
- Updated §5.11.2: synthesis time "under 50ms" → "~73ms average (range 15-296ms)"
- Added new subsection §5.11.3: SORT_STABLE Minimality Override — 17-row encoding, numpy introsort threshold, z3.Distinct timeout fix
- Added new section §5.12: Migration Invariant Selection (MIS) — full section with 5 subsections:
  - Motivation, Candidate Library (18 invariants, 4 categories), Selection Algorithm, 142-pair VTP Corpus + LOO-CV, Application
- Updated §5 Conclusion: added CDAIS 6/6 and MIS mentions

#### chapter7.tex (Evaluation)
- Updated novelty claim #3: CDAIS "deferred to future work" → "fully confirmed" with concrete numbers (6/6 detection, 7.8 avg rows, 73ms)
- Added novelty claim #4: MIS corpus-driven invariant selection (10/18, 142-pair, LOO-CV)
- Added new subsection: CDAIS Evaluation Results — per-class table (RETAIN_RESET through GROUP_BOUNDARY with PTDR, witness rows, synthesis times)
- Added new subsection: MIS Evaluation Results — 10/18 confirmed, 3 demoted/3 promoted, LOO-CV zero fragile, 937ms runtime
- Added MIS strength subsection (§7.6.6)
- Updated Ch7 conclusion: added CDAIS/MIS concrete results paragraph
- Fixed future work: removed "CDAIS full implementation" (done), removed "JOIN/LAG extension" (already in 6 classes)
- Added future work: CDAIS taxonomy expansion (6→20+), automated MIS candidate generation, double annotation for VTP corpus

#### chapter_conclusion.tex
- "five" → "six" scientific contributions
- Added contribution (4): MIS with concrete numbers
- Updated CDAIS contribution (3): added evaluation numbers
- Updated medium-term research: CDAIS extension to 20+ classes, MIS automated generation

### Files Modified
- `report/abstract.tex`
- `report/chapter0_intro.tex`
- `report/chapter1.tex`
- `report/chapter5.tex`
- `report/chapter7.tex`
- `report/chapter_conclusion.tex`
- `docs/logs/19May.md` (this file)
