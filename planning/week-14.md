# Week 14: Buffer — Polish, Extra KB Pairs, Final README

> ⚠️ **Planning document.** For current state, see the root [README.md](../README.md) and [week13Done.md](week13Done.md).

> **Priority**: P3  
> **Branch**: `week-14`  
> **Layer**: All (polish & finalization)  
> **Prerequisite**: Week 13 complete (slides + demo video done)  

---

## 🎯 Goal

Use the buffer week to: finish incomplete items from earlier weeks, add 50 more KB pairs (330 → 380), polish ablation plots for the defense, finalize the README, and finalize defense slides. This week ensures the project is submission-ready with no loose ends.

> **Note (Week 13 update):** Docker Compose, CI/CD, CodeQL, Dependabot, and telemetry are **already done** (delivered in Week 13 alongside agent consolidation). The Docker task below is removed from this week's scope. Focus is now on defense slides, ablation polish, KB expansion, and final documentation.

---

## Task 1: Polish Ablation Plots

**File**: Update `scripts/analyze_ablation.py` and regenerate plots.

### Actions

```bash
# 1. Regenerate plots with publication-quality formatting
python scripts/analyze_ablation.py --db ablation.db --plots

# 2. Verify all 3 plots exist
ls docs/ablation_plots/
# Expected: hit_rate_by_complexity.png, mrr_distribution.png, latency_distribution.png

# 3. Add to slides if not already done
```

### Plot Polish Checklist

```python
# Apply these matplotlib tweaks for defense-quality plots:
import matplotlib.pyplot as plt

plt.rcParams.update({
    "figure.dpi": 150,
    "font.size": 12,
    "axes.titlesize": 14,
    "axes.labelsize": 12,
    "legend.fontsize": 10,
    "figure.figsize": (8, 5),
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.1,
})

# Color scheme (consistent across all plots):
RAPTOR_COLOR = "#2196F3"   # blue
FLAT_COLOR   = "#FF9800"   # orange
TARGET_COLOR = "#E53935"   # red (threshold lines)
```

---

## Task 2: Add 50 More KB Pairs (330 → 380)

### Strategy

Target the categories with the weakest ablation performance. After Week 12's analysis, identify which categories had lowest hit-rate and add pairs there.

```bash
# 1. Identify weak categories
python -c "
import duckdb
conn = duckdb.connect('ablation.db', read_only=True)
results = conn.execute('''
    SELECT r.expected_category, 
           AVG(CAST(a.hit_at_5 AS DOUBLE)) as hit_rate,
           COUNT(*) as n
    FROM ablation_results a
    JOIN ablation_queries q ON a.query_id = q.query_id
    GROUP BY r.expected_category
    ORDER BY hit_rate ASC
    LIMIT 5
''').fetchall()
for r in results:
    print(f'{r[0]}: hit@5={r[1]:.3f} (n={r[2]})')
"

# 2. Generate targeted pairs for weak categories
python scripts/generate_pairs.py --category DATE_ARITHMETIC --count 10
python scripts/generate_pairs.py --category MERGE_SEMANTICS --count 10
python scripts/generate_pairs.py --category MACRO_CONDITIONAL --count 10
python scripts/generate_pairs.py --category DATA_STEP_RETAIN --count 10
python scripts/generate_pairs.py --category MISSING_VALUE_HANDLING --count 10

# 3. Verify new total
python -c "
import lancedb
db = lancedb.connect('lancedb_data')
t = db.open_table('sas_python_examples')
verified = t.to_pandas().query('verified == True')
print(f'Total verified KB pairs: {len(verified)}')
print(f'By category:')
print(verified['category'].value_counts().to_string())
"
```

### KB Changelog Entries

```python
# Log the expansion in kb_changelog
import duckdb
conn = duckdb.connect("analytics.db")

categories_added = [
    ("DATE_ARITHMETIC", 10),
    ("MERGE_SEMANTICS", 10),
    ("MACRO_CONDITIONAL", 10),
    ("DATA_STEP_RETAIN", 10),
    ("MISSING_VALUE_HANDLING", 10),
]

for cat, count in categories_added:
    conn.execute("""
        INSERT INTO kb_changelog
        (changelog_id, example_id, action, old_version, new_version,
         author, diff_summary, created_at)
        VALUES (?, ?, 'insert', NULL, 1, 'llm_gen', ?, NOW())
    """, [
        str(uuid4()),
        f"batch_expansion_{cat}",
        f"Added {count} pairs for {cat} category (Week 14 polish)",
    ])
```

---

## Task 3: Finalize README.md

**File**: Update `README.md` with final content.

### README Final Sections Checklist

```markdown
# README.md — Final Content Checklist

## Sections that must exist:
- [ ] Project title + one-line description
- [ ] Badges (Python version, license, test status)
- [ ] Quick Start (3 commands: install, setup, run)
- [ ] Architecture overview (Mermaid diagram or image link)
- [ ] Features list (16 agents, 6 layers)
- [ ] Installation (pip install, Ollama setup, DB init)
- [ ] Usage examples (CLI, Python API)
- [ ] Configuration (environment variables, config files)
- [ ] Project structure (tree)
- [ ] Evaluation results summary (link to docs/evaluation_summary.md)
- [ ] Contributing (for future developers)
- [ ] License
- [ ] Acknowledgments (RAPTOR paper, supervisor)

## Word count target: ≥ 100 lines (already met from Week 1)
```

### Update Commands

```bash
# Verify current README length
wc -l README.md
# Should be ≥ 100 lines

# Add final project structure tree
python -c "
import os
for root, dirs, files in os.walk('partition'):
    level = root.replace('partition', '').count(os.sep)
    indent = ' ' * 2 * level
    print(f'{indent}{os.path.basename(root)}/')
    sub_indent = ' ' * 2 * (level + 1)
    for file in sorted(files):
        if file.endswith('.py'):
            print(f'{sub_indent}{file}')
" > project_tree.txt
```

### Quick Start Section (ensure it works)

```markdown
## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/your-org/sas-python-accelerator.git
cd sas-python-accelerator
pip install -r requirements.txt

# 2. Start Ollama (required for LLM inference)
ollama serve &
ollama pull llama3.1:8b

# 3. Initialize databases
python scripts/init_databases.py

# 4. Convert a SAS file
python -m partition.orchestrator path/to/your_file.sas --target python

# 5. Check output
cat output/your_file_converted.py
cat output/your_file_report.md
```
```

---

## Task 4: Final Test Suite Run

```bash
# Run ALL tests with coverage report
pytest tests/ --cov=partition --cov-report=html --cov-report=term-missing -v

# Expected output structure:
# tests/
#   test_file_analysis.py       ← Week 1-2
#   test_cross_file_deps.py     ← Week 1-2
#   test_registry_writer.py     ← Week 1-2
#   test_streaming.py           ← Week 2-3
#   test_state_agent.py         ← Week 2-3
#   test_boundary_detector.py   ← Week 3-4
#   test_complexity_agent.py    ← Week 4
#   test_strategy_agent.py      ← Week 4
#   test_raptor.py              ← Week 5-6
#   test_persistence.py         ← Week 7
#   test_index_agent.py         ← Week 7
#   test_orchestrator.py        ← Week 8
#   test_translation.py         ← Week 10
#   test_validation_agent.py    ← Week 10
#   test_import_consolidator.py ← Week 11
#   test_dependency_injector.py ← Week 11
#   test_script_merger.py       ← Week 11
#   test_merge_e2e.py           ← Week 11
#   test_continuous_learning.py ← Week 11
#   regression/
#     test_boundary_accuracy.py ← Week 3-4
#     test_ece.py               ← Week 4
#     test_ablation.py          ← Week 12

# Verify coverage
# Target: ≥ 80% overall (every agent has ≥ 5 assertions)

# Run regression guards specifically
pytest tests/regression/ -v --timeout=60
```

---

## Task 5: requirements.txt — Final Version

**File**: `requirements.txt`

```
# Core
pydantic>=2.0
structlog>=23.1
aiofiles>=23.0

# LLMs
instructor>=0.6
ollama>=0.1
groq>=0.4

# Embedding
nomic>=1.0

# Databases
lancedb>=0.5
duckdb>=0.9
networkx>=3.0

# ML / Evaluation
scikit-learn>=1.3
numpy>=1.24
scipy>=1.11

# NLP / Code Analysis
lark>=1.1
tiktoken>=0.5
radon>=6.0

# Data
pandas>=2.0
pyarrow>=14.0

# Translation quality
codebleu>=0.7

# Report generation
markdown2>=2.4

# Visualization (ablation plots)
matplotlib>=3.8

# Caching / Checkpoints
redis>=5.0

# Testing
pytest>=7.0
pytest-cov>=4.0
pytest-asyncio>=0.21
memray>=1.10

# Dev tools
black>=23.0
ruff>=0.1
```

---

## Task 6: Docker Compose (Optional — Cut #2)

**File**: `docker-compose.yml`

```yaml
# OPTIONAL — only if time permits (Cut #2 in PLANNING.md)
# This is NOT required for the defense but is nice to have.

version: "3.9"

services:
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  app:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      - ollama
      - redis
    environment:
      - OLLAMA_HOST=http://ollama:11434
      - REDIS_HOST=redis
      - GROQ_API_KEY=${GROQ_API_KEY}
    volumes:
      - ./benchmark:/app/benchmark
      - ./output:/app/output
      - ./lancedb_data:/app/lancedb_data
    command: >
      python -m partition.orchestrator
      benchmark/etl_customer.sas
      --target python

volumes:
  ollama_data:
  redis_data:
```

**File**: `Dockerfile` (only if Docker Compose is created)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Default: run tests
CMD ["pytest", "tests/", "-v", "--timeout=120"]
```

---

## Task 7: Final Deliverables Verification

### Verification Script

**File**: `scripts/verify_deliverables.py`

```python
"""
Final deliverables verification script.
Checks all required files exist and meet minimum criteria.

From cahier §13: Code, Data, and Documentation deliverables.

Usage:
    python scripts/verify_deliverables.py
"""

import os
import subprocess
import sys
from pathlib import Path


def check(name: str, condition: bool, detail: str = "") -> bool:
    status = "✓" if condition else "✗"
    suffix = f" ({detail})" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    return condition


def main():
    print("=" * 60)
    print("FINAL DELIVERABLES VERIFICATION")
    print("=" * 60)

    results = []

    # ---- Code Deliverables ----
    print("\n## Code Deliverables")

    # Agent count
    agent_files = list(Path("partition").rglob("*agent*.py"))
    results.append(check(
        "Agent implementations ≥ 12",
        len(agent_files) >= 12,
        f"found {len(agent_files)} agent files",
    ))

    # Test suite
    test_files = list(Path("tests").rglob("test_*.py"))
    results.append(check(
        "Test files ≥ 15",
        len(test_files) >= 15,
        f"found {len(test_files)} test files",
    ))

    # Translation agent
    results.append(check(
        "TranslationAgent exists",
        Path("partition/translation").exists(),
    ))

    # Merge pipeline
    results.append(check(
        "Merge pipeline exists",
        Path("partition/merge").exists(),
    ))

    # Continuous learning
    results.append(check(
        "Continuous learning exists",
        Path("partition/retraining").exists(),
    ))

    # ---- Data Deliverables ----
    print("\n## Data Deliverables")

    results.append(check(
        "LanceDB data directory",
        Path("lancedb_data").is_dir(),
    ))

    results.append(check(
        "Gold standard corpus",
        any(Path("knowledge_base/gold_standard").glob("*.gold.json"))
        if Path("knowledge_base/gold_standard").exists() else False,
    ))

    results.append(check(
        "Complexity training data",
        Path("benchmark/complexity_training.csv").exists(),
    ))

    results.append(check(
        "NetworkX graph data",
        Path("partition_graph").is_dir(),
    ))

    results.append(check(
        "Ablation database",
        Path("ablation.db").exists(),
    ))

    # ---- Documentation Deliverables ----
    print("\n## Documentation Deliverables")

    readme = Path("README.md")
    results.append(check(
        "README.md ≥ 100 lines",
        readme.exists() and len(readme.read_text().splitlines()) >= 100,
        f"{len(readme.read_text().splitlines())} lines" if readme.exists() else "missing",
    ))

    results.append(check(
        "Architecture HTML",
        Path("docs/architecture_v2.html").exists(),
    ))

    raptor_notes = Path("docs/raptor_paper_notes.md")
    if raptor_notes.exists():
        word_count = len(raptor_notes.read_text().split())
        results.append(check(
            "RAPTOR paper notes ≥ 500 words",
            word_count >= 500,
            f"{word_count} words",
        ))
    else:
        results.append(check("RAPTOR paper notes", False, "missing"))

    results.append(check(
        "Ablation results doc",
        Path("docs/ablation_results.md").exists(),
    ))

    results.append(check(
        "Defense slides",
        Path("docs/defense_slides.pptx").exists()
        or Path("docs/defense_slides.pdf").exists(),
    ))

    demo = Path("docs/demo_video.mp4")
    results.append(check(
        "Demo video exists",
        demo.exists(),
    ))

    # ---- Summary ----
    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 60}")
    print(f"RESULT: {passed}/{total} checks passed")
    if passed == total:
        print("🎉 All deliverables verified. Ready for submission.")
    else:
        print(f"⚠️  {total - passed} checks failed. Review above.")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## File Structure After Week 14

```
.
├── README.md                       ← finalized
├── requirements.txt                ← finalized
├── .gitignore                      ← from earlier
├── cahier_des_charges.tex          ← cahier (Overleaf)
├── cahier.txt                      ← authoritative spec
├── docker-compose.yml              ← optional (Cut #2)
├── Dockerfile                      ← optional
├── partition/                      ← all 16 agents
│   ├── agents/
│   ├── boundary/
│   ├── complexity/
│   ├── embedding/
│   ├── evaluation/
│   ├── merge/
│   ├── orchestrator/
│   ├── raptor/
│   ├── retraining/
│   ├── streaming/
│   └── translation/
├── tests/
│   ├── test_*.py                   ← ≥ 15 test files
│   └── regression/
│       ├── test_boundary_accuracy.py
│       ├── test_ece.py
│       └── test_ablation.py
├── scripts/
│   ├── generate_pairs.py
│   ├── expand_kb.py
│   ├── submit_correction.py
│   ├── init_databases.py
│   ├── init_ablation_db.py
│   ├── analyze_ablation.py
│   ├── demo_smoke_test.py
│   └── verify_deliverables.py      ← Task 7
├── docs/
│   ├── architecture_v2.html
│   ├── raptor_paper_notes.md
│   ├── ablation_results.md
│   ├── ablation_plots/
│   ├── evaluation_summary.md
│   ├── defense_slides.pptx
│   ├── demo_script.md
│   └── demo_video.mp4
├── knowledge_base/
│   └── gold_standard/
├── benchmark/
│   ├── etl_customer.sas
│   ├── sales_analysis.sas
│   └── complexity_training.csv
├── lancedb_data/
├── partition_graph/
├── output/
├── planning/
│   ├── PLANNING.md
│   └── week-01-02.md through week-14.md
├── analytics.db
├── partition_store.db
└── ablation.db
```

---

## ✅ Week 14 Success Checklist

| # | Check | Target | Verification |
|---|-------|--------|--------------|
| 1 | Ablation plots polished | Publication quality, consistent colors | Visual review |
| 2 | KB pairs ≥ 380 | 50 more pairs added | LanceDB count |
| 3 | README finalized | ≥ 100 lines, Quick Start works | `wc -l README.md` + follow Quick Start |
| 4 | Full test suite passes | All tests green, coverage ≥ 80% | `pytest tests/ --cov=partition -v` |
| 5 | Regression guards pass | boundary + ECE + ablation | `pytest tests/regression/ -v` |
| 6 | requirements.txt complete | All deps listed with versions | `pip install -r requirements.txt` works |
| 7 | Deliverables verification | All checks pass | `python scripts/verify_deliverables.py` |
| 8 | Evaluation table filled | No blanks in "Achieved" column | Review `docs/evaluation_summary.md` |
| 9 | Git history clean | Semantic commits, weekly branches | `git log --oneline` |
| 10 | Docker Compose (optional) | Runs if created | `docker compose up --build` |

---

## Final Git Operations

```bash
# Ensure all weekly branches are merged
for week in $(seq -w 1 14); do
    git log --oneline main..week-$week 2>/dev/null | head -1
done

# Tag the release
git tag -a v1.0.0 -m "PFE submission: SAS→Python Conversion Accelerator v1.0"
git push origin main --tags

# Generate final commit stats
echo "=== Project Stats ==="
echo "Total commits: $(git log --oneline | wc -l)"
echo "Total files: $(git ls-files | wc -l)"
echo "Total lines: $(git ls-files | xargs wc -l | tail -1)"
echo "Contributors: $(git shortlog -sn | wc -l)"
```

---

## Evaluation Metrics — Week 14

| Metric | Target | How to Measure |
|--------|--------|----------------|
| KB pairs (final) | ≥ 380 | LanceDB table count |
| Test coverage | ≥ 80% | `pytest --cov` |
| All regression guards | Pass | `pytest tests/regression/` |
| Deliverables check | All pass | `python scripts/verify_deliverables.py` |
| README lines | ≥ 100 | `wc -l README.md` |
| Documentation complete | All docs exist | File existence checks |

---

## Common Pitfalls

1. **Forgetting to merge a weekly branch** — Check all 14 branches are merged before tagging v1.0.
2. **requirements.txt version conflicts** — Test `pip install -r requirements.txt` in a fresh venv.
3. **KB expansion without logging** — Every new KB pair must have a `kb_changelog` entry. Don't skip this.
4. **Docker Compose NVIDIA driver** — Only include GPU reservation if the defense machine has NVIDIA. Add a `.env` or conditional.
5. **Ablation plots with wrong data** — If you re-ran the ablation or added KB pairs, regenerate plots from the correct `run_id`.
6. **Demo video references old metrics** — If you re-ran metrics after Week 13's recording, either re-record or add a note that "values in the video reflect the Week 12 run."

---

## 🎓 Project Complete

At the end of Week 14, you should have:

- **16 agents** implemented and tested across 6 layers
- **330+ KB pairs** (target 380 with Week 14 expansion)
- **Ablation study** with quantitative RAPTOR vs flat comparison
- **20-slide defense deck** with filled evaluation table
- **3–5 min demo video** showing end-to-end pipeline
- **Full test suite** with ≥ 80% coverage
- **3 regression guards** (boundary accuracy, ECE, RAPTOR hit-rate)
- **Continuous learning loop** (feedback → KB update → retraining)
- **All documentation** (README, paper notes, ablation report, architecture)

Good luck with the defense! 🎓

---

> *Week 14 — Buffer & Polish — Final Submission*
