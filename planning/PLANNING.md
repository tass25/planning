# SAS → Python/PySpark Conversion Accelerator — 14-Week Master Plan

> ⚠️ **Historical planning document.** For current architecture and state, see the root [README.md](../README.md) and [sas_converter/README.md](../sas_converter/README.md).

> **Methodology**: Hybrid Kanban + Weekly Sprints  
> **Branch strategy**: `week-01`, `week-02`, … merged to `main` every Sunday  
> **WIP limit**: 2 concurrent tasks max  
> **Velocity rule**: if `N_done / N_planned < 0.7` for 2 consecutive weeks → cut optional deliverables  

---

## Priority Legend

| Priority | Meaning | Weeks |
|----------|---------|-------|
| **P0** | Core infrastructure — must be completed first | 1–4 |
| **P1** | RAPTOR semantic layer + persistence — builds on P0 | 5–8 |
| **P2** | Translation, merge, learning, evaluation | 9–12 |
| **P3** | Defense preparation and polish | 13–14 |

---

## Timeline Overview

| Week | Layer | Deliverable | Priority | Key Agents | Success Gate |
|------|-------|-------------|----------|------------|--------------|
| **1–2** | L2-A | Entry + CrossFileDeps + DataLineageExtractor + Gold Standard (50 files, 3 tiers, 721 blocks) | **P0** | FileAnalysisAgent, CrossFileDependencyResolver, RegistryWriterAgent, DataLineageExtractor | 50 files scanned (simple/med/hard), cross_file_deps populated, data_lineage table filled, gold corpus annotated with lineage |
| **2–3** | L2-B | StreamAgent + StateAgent | **P0** | StreamAgent, StateAgent | 10K-line file < 2 s, < 100 MB peak memory |
| **3–4** | L2-C | BoundaryDetector + LLM resolver | **P0** | BoundaryDetectorAgent | 721-block benchmark > 90% boundary accuracy |
| **4** | L2-D | ComplexityAgent + StrategyAgent + models | **P0** | ComplexityAgent, StrategyAgent | ECE < 0.08 on held-out 20% |
| **5–6** | L2-C | Nomic Embed + GMM + ClusterSummarizer + RAPTORTreeBuilder | **P1** | RAPTORPartitionAgent | BIC convergence, clusters formed, summaries cached |
| **7** | L2-E | Persistence + NetworkX graph + SCC + DuckDB schemas | **P1** | PersistenceAgent, IndexAgent | All schemas created, SCC detection ≥ 90% |
| **8** | Orch | Orchestration + Redis + audit logging | **P1** | PartitionOrchestrator | Full L2 pipeline runs end-to-end with checkpoints |
| **9** | Robust | Robustness + large file strategy + KB gen start | P2 | — | 250 KB pairs generated, large-file fallback tested |
| **10** | L3 | TranslationAgent + ValidationAgent (KB at 250 from Week 9) | P2 | TranslationAgent, ValidationAgent | Translation success ≥ 70%, validation gate works |
| **11** | L4+CL | Merge + ReportAgent + Continuous Learning + KB to 330 | P2 | ReportAgent, FeedbackIngestionAgent, ConversionQualityMonitor | Merged scripts ≥ 95% syntax valid, reports generated |
| **12** | Eval | Ablation study: RAPTOR vs flat | P2 | — | RAPTOR hit-rate@5 > 0.82, advantage ≥ 10% on MOD/HIGH |
| **13** | Consolidation | Agent consolidation (21→8) + Enterprise features (telemetry, CI/CD, Docker, security). Audit grade A-. | P3 | — | 8 agents, 7 nodes, v3.0.0, 200 tests pass |
| **14** | Buffer | Defense slides + polish plots + extra KB pairs + README | P3 | — | All docs finalized |

---

## Weekly Sprint Ritual (every Sunday)

1. **Review** — Compute velocity: `N_done / N_planned`
2. **Retrospective** — What went well? What blocked?
3. **Plan** — Pick 3–5 tasks for next week from the weekly detail file
4. **Git merge** — Merge `week-XX` branch to `main` after success checklist passes
5. **Commit convention** — `feat:`, `fix:`, `test:`, `docs:`

---

## Cut Order (if timeline slips)

| Cut # | What to cut | Impact |
|-------|-------------|--------|
| 1 | Workshop paper draft | No deliverable impact |
| 2 | Docker compose setup | ~~No deliverable impact~~ **Delivered in Week 13** |
| 3 | Ablation depth (Week 12) — reduce from 500 to 250 queries | Weaker statistical claim but still valid |
| **NEVER CUT** | Translation Layer (L3) + Merge Layer (L4) | Core pipeline |

---

## Risk Register (Quick Reference)

| Risk | Prob | Impact | Mitigation |
|------|------|--------|------------|
| Groq API quota exceeded | MED | HIGH | 3-tier fallback (Azure OpenAI → Groq free tier → heuristic) |
| RAPTOR ablation null result | LOW | MED | Document as negative result + propose 1K+ pair threshold |
| GMM diverges on large files | MED | HIGH | Fallback to flat_partition after 3 failed fits |
| 14-week timeline slips | HIGH | MED | Sunday velocity tracking + cut order above |
| ECE > 0.08 after retraining | MED | LOW | Relabel 100 more, retrain; worst case: threshold routing |
| Kuzu install fails | LOW | MED | No longer applicable — replaced by NetworkX (pure Python, always available) |
| KB quality too low (avg conf < 0.80) | MED | HIGH | Increase cross-verifier retries to 3 |

---

## Detailed Weekly Files

Each file below contains everything you need for that specific week — tasks, code to write, tests to pass, data structures, exact commands, and the success checklist.

| File | Week(s) |
|------|---------|
| [week-01-02.md](week-01-02.md) | Weeks 1–2: Entry & Scan + Gold Standard |
| [week-02-03.md](week-02-03.md) | Weeks 2–3: Streaming Core |
| [week-03-04.md](week-03-04.md) | Weeks 3–4: Boundary Detection |
| [week-04.md](week-04.md) | Week 4: Complexity & Strategy |
| [week-05-06.md](week-05-06.md) | Weeks 5–6: RAPTOR Chunking |
| [week-07.md](week-07.md) | Week 7: Persistence & Index |
| [week-08.md](week-08.md) | Week 8: Orchestration |
| [week-09.md](week-09.md) | Week 9: Robustness + KB Generation |
| [week-10.md](week-10.md) | Week 10: Translation + Validation |
| [week-11.md](week-11.md) | Week 11: Merge + Report + CL |
| [week-12.md](week-12.md) | Week 12: Ablation Study |
| [week-13.md](week-13.md) | Week 13: Defense Prep |
| [week13Done.md](week13Done.md) | Week 13 Done: Consolidation + Enterprise |
| [week-14.md](week-14.md) | Week 14: Buffer & Polish |

---

> *Master Plan v2.0 — SAS-to-Python/PySpark Conversion Accelerator — 8 Consolidated Agents · 14 Weeks · Pipeline v3.0.0*
