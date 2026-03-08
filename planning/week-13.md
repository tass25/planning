# Week 13: Defense Preparation — Slides + Demo Video

> ⚠️ **Planning document.** For completed work, see [week13Done.md](week13Done.md).

> **Priority**: P3  
> **Branch**: `week-13`  
> **Layer**: Documentation & Presentation  
> **Prerequisite**: Week 12 complete (ablation study done, all pipeline layers functional)  
> **Status**: ⚠️ PLAN CHANGED — Actual delivery was **agent consolidation (21→8) + enterprise features** instead of defense slides. See [week13Done.md](week13Done.md)  
> **What was actually delivered**: Architecture audit (B+ → A-), agent consolidation (21→8, 11→7 nodes, v3.0.0), dead code removal (opencensus, Ollama), enterprise features (telemetry, CI/CD, CodeQL, Dependabot, Docker, docker-compose). Defense slides moved to Week 14.  

---

## 🎯 Goal

Prepare the PFE defense deliverables: a 20-slide presentation and a 3–5 minute demo video. Fill in the "Achieved" column of the evaluation summary table with actual measured values. This week is non-coding — it's about communicating the work clearly and convincingly.

---

## Task 1: Slide Deck Structure (20 Slides)

**File**: `docs/defense_slides.pptx` (or Google Slides / LaTeX Beamer)

### Slide-by-Slide Outline

| Slide # | Title | Content | Duration |
|---------|-------|---------|----------|
| 1 | Title Slide | Project name, student name, supervisor, date, university logo | 10s |
| 2 | Problem Statement | SAS legacy code at enterprise scale; manual migration cost; why automation matters | 30s |
| 3 | Project Objectives | 3 bullets: partition, translate, evaluate. Scope: 15 SAS construct categories | 20s |
| 4 | Existing Solutions | Comparison table: manual, rule-based (SAS2PY), LLM-direct. Limitations of each | 30s |
| 5 | Proposed Architecture (Overview) | High-level 6-layer diagram from architecture_v2.html. "This is what we built." | 30s |
| 6 | Layer 2-A/B: Entry + Streaming | FileAnalysisAgent, CrossFileDeps, StreamAgent, StateAgent. Key metric: 10K lines < 2s | 20s |
| 7 | Layer 2-C: Boundary Detection | Lark grammar + LLM resolver hybrid. Key metric: >90% boundary accuracy | 30s |
| 8 | Layer 2-D: Complexity & Strategy | Platt scaling, 5-feature extraction, ECE < 0.08. Show reliability diagram | 30s |
| 9 | RAPTOR Adaptation | Sarthi et al. ICLR 2024 → code domain. GMM clustering, hierarchical tree. Diagram | 40s |
| 10 | Knowledge Base | 330 pairs, 15 categories, dual-LLM generation, cross-verification, KB versioning | 30s |
| 11 | Translation Layer (L3) | Failure-mode-aware prompting, 3-tier LLM fallback, ValidationAgent sandbox | 30s |
| 12 | Merge Layer (L4) + ReportAgent | ImportConsolidator, DependencyInjector, ScriptMerger, structured report output | 20s |
| 13 | Continuous Learning | FeedbackIngestion, QualityMonitor, 4 retraining triggers | 20s |
| 14 | Technology Stack | Table with key choices: Ollama/Groq, LanceDB, NetworkX, DuckDB, Nomic Embed | 20s |
| 15 | Evaluation: Boundary Accuracy | Table + confusion matrix from gold standard. Target vs achieved | 30s |
| 16 | Evaluation: RAPTOR Ablation | Bar chart from Week 12 (hit-rate by complexity). RAPTOR vs flat advantage | 40s |
| 17 | Evaluation: Translation Quality | success_rate, ECE, CodeBLEU. Quality metrics table (target vs achieved) | 30s |
| 18 | Demo Screenshot / Video Link | Key screenshots: CLI run, report output, merged Python script | 20s |
| 19 | Limitations & Future Work | KB size limitation, PySpark coverage, production deployment considerations | 30s |
| 20 | Conclusion + Q&A | Summary of contributions, thank the jury | 20s |

**Total**: ~8–10 minutes speaking time (with natural pauses). Target: 7 minutes for presentation, 3 minutes Q&A.

---

## Task 2: Slide Content Templates

### Slide 2 — Problem Statement

```
The Problem:
- Enterprise banks run 500K+ lines of SAS across 200+ programs
- Manual migration: 6-12 months, $500K–$2M consulting cost
- SAS license cost: $50K+/year per seat
- Existing tools: rule-based (miss semantics) or raw LLM (hallucinate)

Our approach: Agent-based pipeline with RAG-augmented translation
```

### Slide 5 — Architecture Overview (content for the slide)

```
Use the Mermaid diagram from architecture_v2.html, rendered as PNG.
Annotate with:
- 16 agents across 6 layers
- 3 LLM tiers (local 8B, Groq 70B, heuristic fallback)
- 4 storage systems (SQLite, DuckDB, LanceDB, Redis) + NetworkX graph
- RAPTOR hierarchical tree

Command to render Mermaid to PNG:
  npx @mermaid-js/mermaid-cli mmdc -i arch.mmd -o arch.png -w 1200
```

### Slide 9 — RAPTOR Adaptation

```
Key visual: side-by-side comparison
Left: Original RAPTOR (Sarthi et al.) — text documents → recursive summarization
Right: Our adaptation — SAS code partitions → GMM clustering → code-aware summaries

Differences to highlight:
1. Domain: natural language → structured code
2. Clustering: K-Means → GMM (handles overlapping constructs)
3. Summaries: generic → code-specific (preserve import/variable metadata)
4. Evaluation: QA accuracy → retrieval hit-rate for code translation
```

### Slide 16 — Ablation Results

```
Include directly from docs/ablation_plots/hit_rate_by_complexity.png

Key narrative:
- "RAPTOR achieves X% hit-rate@5 overall (target: >82%)"
- "On MODERATE/HIGH complexity: +Y% advantage over flat retrieval"
- "Validates the hierarchical clustering approach for code semantics"

(Or, if null result): "At 330 KB pairs, RAPTOR matches flat retrieval.
The clustering benefit likely requires ≥1,000 pairs. This establishes a
baseline and identifies the scaling threshold."
```

---

## Task 3: Evaluation Summary Table — Fill "Achieved" Column

**File**: `docs/evaluation_summary.md`

```markdown
# Evaluation Summary — Target vs Achieved

| Metric | Target | Achieved | Status | Evidence |
|--------|--------|----------|--------|----------|
| Boundary accuracy (all blocks) | > 90% | __%% | ☐ | `pytest tests/regression/test_boundary_accuracy.py` |
| Boundary accuracy (complex blocks) | > 85% | __%% | ☐ | Nested macro + PROC SQL subset |
| RAPTOR retrieval hit-rate@5 | > 82% | __%% | ☐ | `SELECT AVG(hit_at_5) FROM ablation_results WHERE index_type='raptor'` |
| RAPTOR vs flat advantage (MOD/HIGH) | ≥ 10% | __%% | ☐ | Stratified DuckDB query |
| ECE (complexity calibration) | < 0.08 | __.__ | ☐ | `pytest tests/regression/test_ece.py` |
| Partition latency (p50) | < 400ms/file | __ms | ☐ | Timing in load test |
| Streaming (10K-line file) | < 2 seconds | __s | ☐ | `pytest tests/test_streaming.py` |
| Peak memory (10K-line file) | < 100 MB | __MB | ☐ | memray profiling |
| Translation success rate | ≥ 70% | __%% | ☐ | DuckDB `quality_metrics` |
| Merged script syntax valid | ≥ 95% | __%% | ☐ | `ast.parse()` on all `merged_scripts` |
| Differential test coverage | 45% | __%% | ☐ | DuckDB `test_coverage_type` distribution |
| KB pairs (verified) | ≥ 330 | __ | ☐ | `python -c "import lancedb; print(len(...))"` |

## How to Fill This Table

Run each evidence command and replace the `__` placeholders with actual values.
Mark status as ✅ (met), ⚠️ (close), or ❌ (missed).
```

### Commands to Collect All Metrics

```bash
# 1. Boundary accuracy
pytest tests/regression/test_boundary_accuracy.py -v 2>&1 | tail -5

# 2. RAPTOR hit-rate
python -c "
import duckdb
conn = duckdb.connect('ablation.db', read_only=True)
hr = conn.execute(\"SELECT AVG(CAST(hit_at_5 AS DOUBLE)) FROM ablation_results WHERE index_type='raptor'\").fetchone()
print(f'RAPTOR hit@5: {hr[0]:.4f}')
"

# 3. RAPTOR advantage
python -c "
import duckdb
conn = duckdb.connect('ablation.db', read_only=True)
r = conn.execute(\"SELECT AVG(CAST(hit_at_5 AS DOUBLE)) FROM ablation_results WHERE index_type='raptor' AND complexity_tier IN ('MODERATE','HIGH')\").fetchone()
f = conn.execute(\"SELECT AVG(CAST(hit_at_5 AS DOUBLE)) FROM ablation_results WHERE index_type='flat' AND complexity_tier IN ('MODERATE','HIGH')\").fetchone()
print(f'RAPTOR MOD/HIGH: {r[0]:.4f}, Flat: {f[0]:.4f}, Advantage: {(r[0]-f[0])*100:.1f}%')
"

# 4. ECE
pytest tests/regression/test_ece.py -v 2>&1 | tail -5

# 5. Streaming latency
pytest tests/test_streaming.py -v 2>&1 | grep -i "latency\|time\|second"

# 6. Peak memory
python -m memray run --output memray_report.bin tests/test_streaming.py
python -m memray stats memray_report.bin | grep "Peak"

# 7. Translation success rate
python -c "
import duckdb
conn = duckdb.connect('analytics.db', read_only=True)
r = conn.execute('SELECT success_rate FROM quality_metrics ORDER BY created_at DESC LIMIT 1').fetchone()
print(f'Success rate: {r[0]:.4f}')
"

# 8. Merged script syntax validity
python -c "
import sqlite3
conn = sqlite3.connect('partition_store.db')
total = conn.execute('SELECT COUNT(*) FROM merged_scripts').fetchone()[0]
valid = conn.execute('SELECT COUNT(*) FROM merged_scripts WHERE syntax_valid=1').fetchone()[0]
print(f'Syntax valid: {valid}/{total} = {valid/total*100:.1f}%')
"

# 9. KB size
python -c "
import lancedb
db = lancedb.connect('lancedb_data')
t = db.open_table('sas_python_examples')
print(f'KB pairs: {len(t.to_pandas())}')
"
```

---

## Task 4: Demo Video Script (3–5 minutes)

**File**: `docs/demo_script.md`

```markdown
# Demo Video Script — 3–5 Minutes

## Setup (before recording)
- Terminal open with project root
- Sample SAS file ready: `benchmark/etl_customer.sas` (20–30 lines, covers 3+ construct types)
- Ollama running: `ollama serve`
- All DBs populated (LanceDB, DuckDB, SQLite) + NetworkX graph built

## Recording Flow

### 0:00–0:30 — Introduction
"This is a demo of the SAS-to-Python Conversion Accelerator.
I'll convert a real SAS ETL script to Python, showing each pipeline stage."

*Show the SAS file briefly in the editor.*

### 0:30–1:00 — Run the Pipeline
```bash
python -m partition.orchestrator benchmark/etl_customer.sas --target python
```

*Show the CLI output: streaming → boundary detection → complexity scoring → RAPTOR tree →
translation → merge → report.*

### 1:00–1:30 — Show Merged Output
*Open `output/etl_customer_converted.py` in the editor.*
"The merged script has:
- Consolidated imports (PEP 8 ordered)
- Translated blocks in original execution order
- TODO stubs for blocks that needed human review"

*Highlight the header comment with block count and partial count.*

### 1:30–2:00 — Show the Conversion Report
*Open `output/etl_customer_report.md` in a Markdown previewer.*
"The ReportAgent generates this for every file:
- Summary table: 4 SUCCESS, 1 PARTIAL, 0 FAILED
- Failure mode breakdown
- CodeBLEU score: 0.62
- KB retrieval stats"

### 2:00–2:30 — Show RAPTOR Tree
*Run a quick query:*
```bash
python -c "
import lancedb
db = lancedb.connect('lancedb_data')
t = db.open_table('raptor_nodes')
df = t.to_pandas()
for level in range(4):
    n = len(df[df['level']==level])
    print(f'Level {level}: {n} nodes')
"
```
"The RAPTOR tree has 3 levels: leaves → L1 clusters → root summaries.
This hierarchical structure improves retrieval for complex blocks."

### 2:30–3:00 — Show DuckDB Analytics
```bash
python -c "
import duckdb
conn = duckdb.connect('analytics.db', read_only=True)
r = conn.execute('SELECT * FROM quality_metrics ORDER BY created_at DESC LIMIT 1').fetchone()
print(f'Success rate: {r[3]:.1%}')
print(f'Avg confidence: {r[6]:.3f}')
"
```
"The continuous learning system monitors translation quality and triggers
retraining when success rate drops below 70%."

### 3:00–3:30 — Show Ablation Result
*Show `docs/ablation_plots/hit_rate_by_complexity.png`.*
"Our ablation study on 500 queries shows RAPTOR achieves X% hit-rate@5,
with a Y% advantage on MODERATE/HIGH complexity blocks."

### 3:30–4:00 — Submit a Correction (Feedback Loop)
```bash
python scripts/submit_correction.py \
    --conversion_id abc123 \
    --python_file corrected_block.py
```
"When a human corrects a translation, the correction is cross-verified
and added to the KB, improving future translations."

### 4:00–4:30 — Wrap Up
"In summary: 16 agents, 6 layers, 330+ KB pairs, continuous learning.
The system converts SAS to Python with 70%+ success rate and produces
structured reports for human reviewers. Thank you."
```

### Recording Tips

```
Tools:
  - OBS Studio (free) or Windows Game Bar (Win+G)
  - Resolution: 1920×1080, 30fps
  - Terminal font: 14pt+ (readable at 720p)
  - Zoom level: 125% in VS Code

Post-production:
  - Trim dead time (pauses, typos)
  - Add subtitles if time permits
  - Export as MP4, target 3–5 minutes
  - Save as: docs/demo_video.mp4
```

---

## Task 5: RAPTOR Paper Notes

**File**: `docs/raptor_paper_notes.md`

```markdown
# RAPTOR Paper Notes — Sarthi et al. (ICLR 2024)

## Citation
Sarthi, P., Abdullah, S., Tuli, A., Khanna, S., Goldie, A., & Manning, C. D. (2024).
RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval.
*International Conference on Learning Representations (ICLR)*.

## Key Idea
Build a hierarchical tree of text chunks:
1. Embed document chunks (leaves)
2. Cluster similar chunks (K-Means in paper → we use GMM)
3. Summarize each cluster with an LLM
4. Embed the summaries → add as new nodes
5. Repeat recursively until root
6. At retrieval: search all levels of the tree

## Why It Works
- Standard flat retrieval misses long-range dependencies
- Hierarchical summaries capture document-level themes
- Multi-level search provides context at different granularities
- Especially beneficial for questions requiring synthesis across sections

## Our Adaptation (Differences from Paper)

| Aspect | Original RAPTOR | Our Adaptation |
|--------|----------------|----------------|
| Domain | Natural language documents | SAS code partitions |
| Clustering | K-Means (fixed k) | GMM (automatic k via BIC; handles overlap) |
| Embedding | Text embedding (generic) | Nomic Embed v1.5 (code-aware, 768-dim) |
| Summarization | GPT-4 | Llama 3.1 70B (Groq) → 8B (Ollama) fallback |
| Leaf content | Raw text paragraphs | PartitionIR (structured SAS blocks with metadata) |
| Evaluation | QA accuracy (NarrativeQA, QASPER) | Retrieval hit-rate@5 for code translation |
| Retrieval query | Natural language question | "Convert SAS {construct} to Python {target}" |
| Practical use | Answer questions about documents | Find relevant KB pairs for code translation |

## Key Numbers from the Paper
- NarrativeQA: +3.2% accuracy over flat retrieval
- QASPER: +2.8% accuracy
- Quality dataset: +1.5%
- Best with recursive tree depth 3+
- K-Means with k=ceil(n/10) for initial clustering

## Our Expected Results
- Hit-rate@5 > 0.82 (higher ceiling expected because domain is narrower)
- Advantage on MODERATE/HIGH: ≥ 10%
- LOW complexity: minimal advantage (simple blocks don't benefit from hierarchy)
- Tree depth: typically 2–3 levels with 330 KB pairs (paper used 1000+ chunks)

## Relevance for Defense
- Shows direct connection between state-of-the-art IR research and industrial SAS migration
- GMM > K-Means is a justified engineering decision (SAS constructs overlap: a PROC SQL with MERGE BY touches two categories)
- Ablation study in Week 12 validates (or honestly refutes) the adaptation
- Even a null result is publishable: "RAPTOR requires ≥1,000 code examples to show advantage"

## BibTeX
```bibtex
@inproceedings{sarthi2024raptor,
  title={RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval},
  author={Sarthi, Parth and Abdullah, Salman and Tuli, Aditi and Khanna, Shubh and Goldie, Anna and Manning, Christopher D},
  booktitle={International Conference on Learning Representations},
  year={2024}
}
```
```

---

## Task 6: End-to-End Pipeline Smoke Test for Demo

**File**: `scripts/demo_smoke_test.py`

```python
"""
Smoke test to verify the full pipeline works before recording the demo.
Runs the complete flow on a small SAS file and checks all outputs exist.

Usage:
    python scripts/demo_smoke_test.py
"""

import subprocess
import sys
from pathlib import Path


CHECKS = [
    ("Benchmark file exists", lambda: Path("benchmark/etl_customer.sas").exists()),
    ("Ollama reachable", lambda: _check_ollama()),
    ("LanceDB data exists", lambda: Path("lancedb_data").is_dir()),
    ("DuckDB analytics exists", lambda: Path("analytics.db").exists()),
    ("SQLite store exists", lambda: Path("partition_store.db").exists()),
    ("Output dir exists", lambda: Path("output").is_dir() or True),  # will be created
]


def _check_ollama() -> bool:
    """Check if Ollama is running."""
    try:
        import requests
        r = requests.get("http://localhost:11434/api/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def main():
    print("=" * 60)
    print("DEMO SMOKE TEST")
    print("=" * 60)

    all_pass = True
    for name, check_fn in CHECKS:
        try:
            result = check_fn()
            status = "✓" if result else "✗"
            if not result:
                all_pass = False
        except Exception as e:
            status = "✗"
            all_pass = False
            result = str(e)
        print(f"  [{status}] {name}")

    print()
    if all_pass:
        print("All pre-flight checks passed. Ready to record demo.")
    else:
        print("Some checks failed. Fix before recording.")
        sys.exit(1)

    # Run pipeline on demo file
    print("\nRunning pipeline on demo file...")
    result = subprocess.run(
        [sys.executable, "-m", "partition.orchestrator",
         "benchmark/etl_customer.sas", "--target", "python"],
        capture_output=True, text=True, timeout=120,
    )

    if result.returncode == 0:
        print("Pipeline completed successfully.")
    else:
        print(f"Pipeline failed:\n{result.stderr}")
        sys.exit(1)

    # Verify outputs
    post_checks = [
        ("Converted script", lambda: any(Path("output").glob("*_converted.py"))),
        ("Report MD", lambda: any(Path("output").glob("*_report.md"))),
        ("Report HTML", lambda: any(Path("output").glob("*_report.html"))),
    ]

    print("\nPost-pipeline checks:")
    for name, check_fn in post_checks:
        result = check_fn()
        status = "✓" if result else "✗"
        print(f"  [{status}] {name}")

    print("\n✓ Demo smoke test complete.")


if __name__ == "__main__":
    main()
```

---

## File Structure After Week 13

```
docs/
├── defense_slides.pptx              ← Task 1 (20 slides)
├── evaluation_summary.md            ← Task 3 (target vs achieved)
├── demo_script.md                   ← Task 4 (video script)
├── demo_video.mp4                   ← Task 4 (recorded video)
├── raptor_paper_notes.md            ← Task 5 (≥ 500 words)
├── ablation_results.md              (from Week 12)
├── ablation_plots/                  (from Week 12)
│   ├── hit_rate_by_complexity.png
│   ├── mrr_distribution.png
│   └── latency_distribution.png
├── architecture_v2.html             (from Week 1)
scripts/
├── demo_smoke_test.py               ← Task 6
```

---

## ✅ Week 13 Success Checklist

| # | Check | Target | Verification |
|---|-------|--------|--------------|
| 1 | Slide count | ≥ 20 slides | Open `.pptx`, count slides |
| 2 | All architecture layers covered | 6 layers + RAPTOR + KB + CL | Review slides 5–13 |
| 3 | Evaluation table filled | All 12 metrics have "Achieved" values | Review `docs/evaluation_summary.md` |
| 4 | Ablation plot in slides | Bar chart from Week 12 | Visual check slide 16 |
| 5 | Demo video recorded | 3–5 min, MP4 | `ffprobe docs/demo_video.mp4` → duration 180–300s |
| 6 | Demo video shows pipeline | CLI → output → report → analytics | Watch video |
| 7 | RAPTOR paper notes | ≥ 500 words | `wc -w docs/raptor_paper_notes.md` |
| 8 | Demo smoke test passes | All checks green | `python scripts/demo_smoke_test.py` |
| 9 | Slides timing | ~7 min total speaking | Practice run with timer |
| 10 | Q&A prep | Anticipated questions listed | Notes in slide notes |

---

## Anticipated Jury Questions (Prepare Answers)

| # | Question | Key Points for Answer |
|---|----------|----------------------|
| 1 | "Why not just use GPT-4 directly?" | Cost ($250/run on 500K lines), no reproducibility, no local inference, no KB learning loop. Our 3-tier fallback is free. |
| 2 | "How do you handle SAS macros?" | MACRO_BASIC + MACRO_CONDITIONAL categories in KB. Nested macros up to depth 3 tested. ComplexityAgent flags HIGH for nested macros → Groq 70B. |
| 3 | "What if RAPTOR doesn't help?" | Honest ablation study. If null result: document clustering threshold, propose 1,000+ pairs. Flat retrieval still works as fallback. |
| 4 | "How confident are you in the calibration?" | ECE < 0.08 on held-out 20%. Platt scaling + reliability diagram. If ECE drifts > 0.12, automatic retraining triggers. |
| 5 | "Can this scale to 10,000 files?" | StreamAgent + Redis checkpoints + SHA-256 dedup enable restart. DuckDB analytics scale to millions of rows. NetworkX graph handles cross-file deps. |
| 6 | "What are the limitations?" | KB size (330, not 10,000). PySpark coverage (basic). No SAS runtime for differential testing. Single-developer timeline. |
| 7 | "Why Nomic Embed over OpenAI embeddings?" | Free, local, 768-dim sufficient, Matryoshka support for dimension reduction. OpenAI = $0.0001/1K tokens, not free. |
| 8 | "What's the failure rate?" | ~30% PARTIAL or HUMAN_REVIEW (target ≥70% success). DATE_ARITHMETIC and MERGE_SEMANTICS are hardest — addressed by failure-mode-aware prompting. |

---

## Common Pitfalls

1. **Slides too text-heavy** — Use visuals (architecture diagram, bar charts, code snippets). Max 5 bullet points per slide, max 7 words per bullet.
2. **Demo fails during recording** — Run `demo_smoke_test.py` first. Have a backup pre-recorded run.
3. **Evaluation table with blanks** — Fill ALL metrics before defense. If a metric wasn't measured, say "not measured due to [reason]" — don't leave blanks.
4. **Misquoting the paper** — The paper is RAPTOR, Sarthi et al., ICLR 2024. Not ICML, not 2023. Double-check the BibTeX.
5. **Demo video too long** — Trim ruthlessly. 3 minutes is better than 5 with dead time. Record in segments, not one take.
6. **Forgetting to mention PySpark** — The project supports both Python and PySpark targets. Mention this explicitly on slide 10 or 11.

---

> *Week 13 — Defense Preparation: Slides + Demo Video*
