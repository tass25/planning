# 20 May 2026 — Session Log

## Terminology Standardisation Across All Report Chapters (Continued)

Completed the systematic terminology replacement across all remaining report chapters. The goal: reserve "agent" exclusively for the two true LLM agents (TranslationAgent, ValidationAgent), and use "stage" / "processing module" for the six deterministic pipeline components.

### Files Edited This Session

**chapter3.tex (Project Specifications)**
- Line 425: "eight-node LangGraph pipeline" → "eight-stage LangGraph pipeline"

**chapter5.tex (Knowledge Integration and Pipeline Implementation)**
- All "Node X" references (lines 48, 95, 150, 1391-1397, 1416-1417) → "Stage X"
- Line 747: "The agent follows" → "The module follows" (Z3VerificationAgent is deterministic, not a true agent)
- Line 1333: "Downstream agents" → "Downstream components"

**chapter6.tex (Deployment and User Interface)**
- Line 95: "8-node LangGraph pipeline" → "8-stage LangGraph pipeline"
- Line 441: "8-node pipeline" → "8-stage pipeline"

**chapter7.tex (Evaluation, Results, and Discussion)**
- Line 244: "Node 4 execution time" → "Stage 4 execution time"
- Line 793: "Z3 agent" → "Z3 verifier"
- Line 904: "macro-resolution agent" → "macro pre-processor"

**chapter_conclusion.tex (General Conclusion)**
- Line 16: "eight-node LangGraph pipeline" → "eight-stage LangGraph pipeline"

**chapter0_intro.tex (General Introduction) — leftover fix**
- Line 79: "eight-node pipeline design" → "eight-stage pipeline design"

**chapter1.tex (Project Context) — leftover fixes**
- Line 35: "eight orchestrated agents" → "eight orchestrated stages"
- Lines 349-350: "8-node" → "8-stage", "multi-agent" → "agentic" in figure caption
- Line 361: "eight-node translation" → "eight-stage translation"
- Line 432: "multi-agent" → "agentic" (DSR suggestion)
- Line 496: "8-node LangGraph" → "8-stage LangGraph" (sprint table)
- Line 500: "node consolidation" → "stage consolidation"
- Line 518: "multi-agent" → "agentic" (chapter conclusion)

**chapter4.tex (Architecture) — leftover fixes**
- Line 27: "eight-node" → "eight-stage" in chapter intro
- All "Node X" section headings (1-8) → "Stage X"
- "sub-agents" → "sub-modules" (lines 356, 482)
- "downstream agents" → "downstream stages" (line 368)
- "8-node pipeline" → "8-stage pipeline" (line 652)
- "all agents" → "all pipeline components" (line 658)

### Verification
- Final grep confirms zero remaining "multi-agent" / "eight-node" / "8-node" / "Node X" / "sub-agent" instances in report chapters (except chapter2 literature references which correctly describe MAS academic field)
- All "agents" plural uses verified as correct — either refer to TranslationAgent/ValidationAgent or to related work literature

## Em Dash (`---`) Elimination

Removed all `---` (em dash) instances from the entire report. Each replacement was context-appropriate:
- **Parenthetical appositives**: `X --- appositive --- Y` → `X (appositive) Y` or `X, appositive, Y`
- **Introductory/explanatory**: `X --- explanation` → `X: explanation` or `X, explanation`
- **Labels (Stage/Tier/Layer/Pattern/Scenario)**: `Label --- Name` → `Label: Name`
- **Table placeholders**: `---` → `--` (en dash)
- **Comment separators**: `% ---------------------------------------------------------------------------` → `%`
- **main.tex comments**: `% --- Section ---` → `% Section`

### Files Edited
All 10 .tex files: main, chapter0_intro through chapter7, chapter_conclusion, acknowledgements

### Verification
- Final grep confirms **zero** remaining `---` across all .tex files

## Citation Conversion (`[X]` → `\cite{key}`)

Replaced all hardcoded `~[X]` inline references with proper `\cite{key}` BibTeX commands. Created `main.tex` with natbib + hyperref for clickable `[1]` style citations.

### Citation Mappings Applied

**Chapter 2** (3 citations):
- `[24]` → `\cite{barr2015oracle}`, `[35]` → `\cite{chakraborty2022codit}`, `[36]` → `\cite{chen2018metamorphic}`

**Chapter 4** (11 citations):
- `[1]` → `\cite{langgraph2024}`, `[2]` → `\cite{crewai2024}`, `[3]` → `\cite{wu2024autogen}`
- `[4]` → `\cite{nygard2018releaseit}`, `[5]` → `\cite{nussbaum2024nomic}`
- `[6]` → `\cite{lancedb2024}`, `[7]` → `\cite{chroma2024}`, `[8]` → `\cite{weaviate2024}`
- `[9]` → `\cite{johnson2021faiss}`, `[10]` → `\cite{demoura2008z3}`, `[11]` → `\cite{maciver2019hypothesis}`

**Chapter 5** (5 citations):
- `[1]` (Poincaré) → `\cite{nickel2017poincare}`, `[1]` (Z3) → `\cite{demoura2008z3}`
- `[2]` → `\cite{weiser1984slicing}`, `[3]` → `\cite{ren2020codebleu}`, `[5]` → `\cite{lahiri2022interactive}`

**Chapter 6** (11 citations):
- `[1]` → `\cite{fastapi2024}`, `[2]` → `\cite{docker2024}`, `[3]` → `\cite{dockercompose2024}`
- `[4]` → `\cite{githubactions2024}`, `[5]` → `\cite{azurekeyvault2024}`
- `[6]` → `\cite{react2024}`, `[7]` → `\cite{vite2024}`, `[8]` → `\cite{typescript2024}`
- `[9]` → `\cite{tailwind2024}`, `[10]` → `\cite{shadcn2024}`, `[11]` → `\cite{zustand2024}`

**Chapter 7** (2 citations):
- `[1]` → `\cite{roziere2020transcoder}`, `[2]` → `\cite{zhu2023codetransocean}`

### Reference Comment Blocks Removed
Removed `% [1] ...` through `% [36] ...` comment blocks from end of chapters 2, 4, 5, 6, 7.

### Verification
- Final grep confirms **zero** remaining `~[X]` hardcoded references across all .tex files
- All 50+ BibTeX entries in `references.bib` are properly keyed and cited via `\cite{}`

## Session — 25 May 2026
- Created docs/defense_qa.md: 50 Q&A covering intro → methodology → implementation → research paper → hard jury attacks
- Full paper coverage: CDAIS, MIS, Z3, 6 error classes, LOO-CV, coverage certificates, Soundness theorem, datasets TC/GSC/VTP, ablation
