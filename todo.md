# Codara Thesis — Evidence & Benchmarking TODO

Every item below is a claim, design decision, or metric in `content.tex` that currently
has no backing data. For each one: what file to create, what to run, where the result goes.

---

## Priority key
- 🔴 **CRITICAL** — number is quoted verbatim in the thesis (abstract, chapter 7). If it's wrong, the thesis fails.
- 🟠 **HIGH** — major design decision or comparison table. Jury will ask about it.
- 🟡 **MEDIUM** — supporting evidence; weak without it but not fatal.
- 🟢 **LOW** — qualitative table, can be built from literature + common sense.

---

## BLOCK 1 — Chapter 1: Existing Solutions Comparison (§1.4.2)

### TODO-01 🟠 Comparison table: Codara vs existing SAS migration tools
**Missing:** Table 1.1 in §1.4.2 — "Study and Critique of Existing Solutions"
**Claim to justify:** "All existing tools lack semantic equivalence checking."

**File to create:** `docs/eval/tool_comparison.md`

**What to put in it:**
Build a 6-column table manually from product documentation and literature:

| Tool | SAS Dialect Coverage | Semantic Verification | Cross-file Deps | Scalability | Open Source | Cost |
|------|---------------------|----------------------|-----------------|-------------|-------------|------|
| SAS Migration Accelerator (SAS Institute) | DATA/PROC/SQL | None | Partial | High | No | Enterprise licence |
| Castalia Systems SAS→Python | DATA/PROC | None | None | Medium | No | Paid |
| Manual rewrite | Full (human) | Manual testing | Yes | Low | — | High labour cost |
| General LLM (GPT-4 zero-shot) | Partial | None | None | Low | No | Per-token |
| **Codara** | DATA/PROC/Macro/Hash | Z3 SMT (4 patterns) | Yes (NetworkX) | High | Yes | Self-hosted |

**Run:** Nothing to run. Research each tool's documentation.
Sources: SAS Institute docs, Castalia website, academic papers in §2.6.1.

**Output goes to:** `content.tex` §1.4.2, Table 1.1.

---

### TODO-02 🟡 Methodology comparison table (§1.5.5)
**Missing:** Table 1.2 in §1.5.5 — "Comparison of Methodologies"

**File to create:** `docs/eval/methodology_comparison.md`

**What to put in it:**

| Criterion | Agile (Scrum) | CRISP-DM | V-Model / SDLC | DSR |
|-----------|--------------|----------|----------------|-----|
| Primary focus | Iterative delivery | Data pipeline | Requirements traceability | Artefact construction |
| Evaluation moment | Each sprint | Deployment phase | Verification & validation gates | Ongoing (built-in) |
| Handles research uncertainty | Yes | Partial | No | Yes |
| Suitability for AI artefacts | Medium | High (data phase) | Low | High |
| Used in Codara | ✓ (sprint structure) | ✓ (KB construction) | Partial | ✓ (primary) |

**Output goes to:** `content.tex` §1.5.5, Table 1.2.

---

## BLOCK 2 — Chapter 4: Technology Selection (§4.2)

### TODO-03 🟠 Orchestration framework selection — feature matrix (§4.2.1)
**Missing:** Table 4.1 in §4.2.1 — "Multi-Agent Orchestration Framework Selection"
**Claim to justify:** "LangGraph wins on stateful resumption and typed state."

**File to create:** `docs/eval/bench_orchestration.md`

**What to put in it — run these quick tests:**

```python
# File: docs/eval/bench_orchestration_timing.py
# Tests: basic 3-node pipeline in each framework, measures init time + step time

import time

# Test 1: LangGraph
from langgraph.graph import StateGraph
from typing import TypedDict

class S(TypedDict):
    x: int

def node_a(s): return {"x": s["x"] + 1}
def node_b(s): return {"x": s["x"] * 2}
def node_c(s): return {"x": s["x"] - 1}

t0 = time.perf_counter()
g = StateGraph(S)
g.add_node("a", node_a)
g.add_node("b", node_b)
g.add_node("c", node_c)
g.add_edge("a", "b")
g.add_edge("b", "c")
g.set_entry_point("a")
g.set_finish_point("c")
app = g.compile()
result = app.invoke({"x": 1})
t1 = time.perf_counter()
print(f"LangGraph 3-node: {(t1-t0)*1000:.1f}ms, result={result}")
```

Then build the feature matrix manually from docs:

| Feature | LangGraph | LangChain LCEL | AutoGen | CrewAI |
|---------|-----------|----------------|---------|--------|
| Typed state (TypedDict) | ✓ | ✗ | ✗ | ✗ |
| Conditional edges | ✓ | Partial | ✓ | ✗ |
| Redis checkpointing | ✓ (built-in) | ✗ | ✗ | ✗ |
| Async-native | ✓ | ✓ | Partial | ✗ |
| Python 3.11 compat | ✓ | ✓ | ✓ | ✓ |
| 3-node init time (ms) | X | X | X | X |

Fill X values from the timing script above.

**Output goes to:** `content.tex` §4.2.1, Table 4.1.

---

### TODO-04 🔴 LLM benchmarking on torture test (§4.2.2)
**Missing:** Table 4.2 in §4.2.2 — "Large Language Model Benchmarking"
**Claim to justify:** "minimax-m2.7:cloud scores 10/10 on torture_test → promoted to PRIMARY"

**File to create:** `docs/eval/bench_llm_models.py`

```python
# docs/eval/bench_llm_models.py
# Run each model on torture_test.sas (10 SAS blocks), record:
#   pass@1 (syntax-valid Python), latency per block, estimated cost
#
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_llm_models.py
#
# Prerequisites: API keys in .env, Ollama running with each model pulled

from __future__ import annotations
import json, time, ast, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "backend"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).parents[2] / ".env")

from partition.utils.llm_clients import (
    get_ollama_client, get_ollama_model,
    get_azure_openai_client, get_groq_openai_client
)

TORTURE_SAS = Path(__file__).parents[2] / "backend/tests/fixtures/torture_test.sas"
PROMPT_TMPL = """\
Convert this SAS block to Python/Pandas. Return only valid Python code, no markdown.

SAS:
{sas}

Python:"""

MODELS = [
    # (label, client_fn, model_name, cost_per_1k_input, cost_per_1k_output)
    ("minimax-m2.7:cloud (Ollama)", "ollama", "minimax-m2.7:cloud",  0.0, 0.0),
    ("gpt-4o-mini (Azure)",         "azure",  "gpt-4o-mini",          0.00015, 0.0006),
    ("gpt-4o (Azure)",              "azure",  "gpt-4o",               0.005,   0.015),
    ("llama-3.3-70b (Groq)",        "groq",   "llama-3.3-70b-versatile", 0.00059, 0.00079),
]

# Split torture test into 10 blocks on blank lines
raw = TORTURE_SAS.read_text()
blocks = [b.strip() for b in raw.split("\n\n") if b.strip()][:10]

results = []
for label, client_type, model, cost_in, cost_out in MODELS:
    passes = 0
    latencies = []
    tokens_in_total = tokens_out_total = 0
    for block in blocks:
        prompt = PROMPT_TMPL.format(sas=block)
        try:
            if client_type == "ollama":
                client = get_ollama_client()
                t0 = time.perf_counter()
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024
                )
            elif client_type == "azure":
                client = get_azure_openai_client()
                t0 = time.perf_counter()
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024
                )
            else:
                client = get_groq_openai_client()
                t0 = time.perf_counter()
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024
                )
            latencies.append(time.perf_counter() - t0)
            code = resp.choices[0].message.content.strip()
            tokens_in_total  += resp.usage.prompt_tokens
            tokens_out_total += resp.usage.completion_tokens
            ast.parse(code)   # syntax check
            passes += 1
        except Exception as e:
            latencies.append(0)

    cost = (tokens_in_total / 1000) * cost_in + (tokens_out_total / 1000) * cost_out
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    results.append({
        "model": label, "pass@1": f"{passes}/10",
        "avg_latency_s": round(avg_lat, 2),
        "tokens_in": tokens_in_total, "tokens_out": tokens_out_total,
        "cost_usd": round(cost, 4)
    })
    print(results[-1])

out = Path(__file__).parent / "bench_llm_results.json"
out.write_text(json.dumps(results, indent=2))
print(f"\nSaved → {out}")
```

**Run:**
```bash
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_llm_models.py
```

**Output goes to:** `content.tex` §4.2.2, Table 4.2.
Columns: Model | Provider | pass@1 (10-block torture) | Avg latency (s) | Cost per 10-block run (USD)

---

### TODO-05 🟠 Embedding model comparison (§4.2.3)
**Missing:** Table 4.3 in §4.2.3 — "Embedding Model and Vector Store Selection"
**Claim to justify:** "Nomic Embed v1.5 chosen over text-embedding-ada-002, BGE-M3, all-MiniLM-L6"

**File to create:** `docs/eval/bench_embeddings.py`

```python
# docs/eval/bench_embeddings.py
# For each embedding model: load 50 KB pairs, embed all, then for 10 query
# blocks compute hit@5 (is the correct pair in top-5 by cosine distance?).
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_embeddings.py

from __future__ import annotations
import json, time, numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

KB_FILE = Path("backend/knowledge_base/gold_standard")  # .sas files as corpus proxy
MODELS = [
    ("all-MiniLM-L6-v2",          384),
    ("nomic-ai/nomic-embed-text-v1.5", 768),
    ("BAAI/bge-m3",               1024),
]

# Load 50 SAS source snippets as "corpus"
sas_files = sorted(KB_FILE.glob("*.sas"))[:50]
corpus = [f.read_text(errors="ignore")[:500] for f in sas_files]
queries = corpus[:10]   # first 10 are both query and expected top-1

for model_name, dim in MODELS:
    print(f"\n--- {model_name} ---")
    t0 = time.perf_counter()
    model = SentenceTransformer(model_name, trust_remote_code=True)
    corpus_emb = model.encode(corpus, batch_size=16, normalize_embeddings=True)
    query_emb  = model.encode(queries,  batch_size=8,  normalize_embeddings=True)
    embed_time = time.perf_counter() - t0

    hits = 0
    for i, q in enumerate(query_emb):
        sims = cosine_similarity([q], corpus_emb)[0]
        top5 = np.argsort(sims)[::-1][:5]
        if i in top5:
            hits += 1

    print(f"  hit@5: {hits}/10  |  embed time: {embed_time:.2f}s  |  dim: {dim}")
```

Build the final table manually after running:

| Model | Dim | hit@5 (50-corpus) | Embed time (50 docs, s) | Licence | CPU-feasible |
|-------|-----|-------------------|-------------------------|---------|-------------|
| all-MiniLM-L6-v2 | 384 | X/10 | X | Apache-2 | ✓ |
| nomic-embed-text-v1.5 | 768 | X/10 | X | Apache-2 | ✓ |
| BAAI/bge-m3 | 1024 | X/10 | X | MIT | Slow |
| text-embedding-ada-002 | 1536 | — | API call | OpenAI ToS | API only |

**Run:**
```bash
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_embeddings.py
```

**Output goes to:** `content.tex` §4.2.3, Table 4.3.

---

### TODO-06 🟡 Z3 vs alternative SMT solvers (§4.2.4)
**Missing:** Table 4.4 in §4.2.4 — "Formal Verification Tool Selection"

**File to create:** `docs/eval/bench_smt_solvers.md`

Build manually — no code needed (CVC5 and Dafny don't need to be run, just compare on paper):

| Criterion | Z3 (Microsoft) | CVC5 | Dafny | Manual test-based |
|-----------|---------------|------|-------|-------------------|
| Python API | ✓ (z3-solver) | ✓ (pycvc5) | ✗ | N/A |
| Linear arithmetic theory | ✓ | ✓ | ✓ | N/A |
| Array theory | ✓ | ✓ | Partial | N/A |
| CEGAR support (programmatic counterexample) | ✓ | ✓ | ✗ | ✗ |
| PyPI installable | ✓ | Partial | ✗ | N/A |
| Active maintenance (2024) | ✓ | ✓ | ✓ | N/A |
| Prior use in code verification | Extensive | Moderate | Moderate | N/A |
| **Decision** | ✓ selected | Fallback | Rejected | Rejected |

**Output goes to:** `content.tex` §4.2.4, Table 4.4.

---

### TODO-07 🟠 Corpus statistics — risk distribution + partition type counts (§4.5.4)
**Missing:** Figure 4.1 + Table 4.5 in §4.5.4 — "Corpus Statistics"
**Claim to justify:** "LOW 38%, MOD 35%, HIGH 21%, UNCERTAIN 6% across 721 blocks"

**File to create:** `docs/eval/corpus_stats.py`

```python
# docs/eval/corpus_stats.py
# Reads all .gold.json files in knowledge_base/gold_standard/ and computes:
#   - total block count
#   - risk level distribution
#   - partition type distribution
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/corpus_stats.py

from __future__ import annotations
import json
from pathlib import Path
from collections import Counter

GOLD_DIR = Path("backend/knowledge_base/gold_standard")

risk_counts = Counter()
type_counts = Counter()
total = 0

for f in sorted(GOLD_DIR.glob("*.gold.json")):
    data = json.loads(f.read_text())
    blocks = data.get("blocks", data.get("partitions", []))
    for b in blocks:
        total += 1
        risk_counts[b.get("risk_level", "UNKNOWN")] += 1
        type_counts[b.get("partition_type", "UNKNOWN")] += 1

print(f"Total blocks: {total}")
print("\nRisk level distribution:")
for k, v in sorted(risk_counts.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v} ({v/total*100:.1f}%)")

print("\nPartition type distribution:")
for k, v in sorted(type_counts.items(), key=lambda x: -x[1]):
    print(f"  {k}: {v} ({v/total*100:.1f}%)")

# Save for plotting
out = {"total": total, "risk": dict(risk_counts), "types": dict(type_counts)}
Path("docs/eval/corpus_stats.json").write_text(json.dumps(out, indent=2))
```

**Run:**
```bash
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/corpus_stats.py
```

Use the `risk` dict to draw a bar chart (matplotlib) → save as `docs/eval/figures/corpus_risk_dist.png`
Use the `types` dict for a second bar chart → `docs/eval/figures/corpus_type_dist.png`

**Output goes to:** `content.tex` §4.5.4, Table 4.5 (numbers) + Figure 4.1 (risk histogram).

---

## BLOCK 3 — Chapter 7: Boundary Detection (§7.2)

### TODO-08 🔴 Boundary detection F1 per partition type (§7.2.1)
**Missing:** Table 7.1 in §7.2.1 — Precision / Recall / F1 per partition type
**Claim to justify:** "79.3% F1 on 721-block gold corpus"

**File to create:** `docs/eval/bench_boundary.py`

```python
# docs/eval/bench_boundary.py
# For each .sas file in gold_standard/, run BoundaryDetectorAgent and compare
# detected boundaries against .gold.json ground truth.
# Computes per-type and global precision / recall / F1.
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_boundary.py

from __future__ import annotations
import json, asyncio, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parents[2] / "backend"))

from partition.chunking.boundary_detector import BoundaryDetectorAgent

GOLD_DIR = Path("backend/knowledge_base/gold_standard")

async def main():
    agent = BoundaryDetectorAgent()
    tp = defaultdict(int); fp = defaultdict(int); fn = defaultdict(int)

    for sas_file in sorted(GOLD_DIR.glob("*.sas")):
        gold_file = sas_file.with_suffix(".gold.json")
        if not gold_file.exists():
            continue
        gold = json.loads(gold_file.read_text())
        gold_blocks = gold.get("blocks", gold.get("partitions", []))
        gold_types  = [(b["line_start"], b["line_end"], b["partition_type"])
                       for b in gold_blocks]

        source = sas_file.read_text()
        predicted = await agent.detect(source)  # returns list of PartitionIR

        pred_set  = {(p.line_start, p.line_end, p.partition_type.value) for p in predicted}
        gold_set  = {(s, e, t) for s, e, t in gold_types}

        for item in pred_set & gold_set:
            tp[item[2]] += 1
        for item in pred_set - gold_set:
            fp[item[2]] += 1
        for item in gold_set - pred_set:
            fn[item[2]] += 1

    all_types = set(tp) | set(fp) | set(fn)
    rows = []
    g_tp = g_fp = g_fn = 0
    for t in sorted(all_types):
        p  = tp[t] / (tp[t] + fp[t]) if (tp[t]+fp[t]) else 0
        r  = tp[t] / (tp[t] + fn[t]) if (tp[t]+fn[t]) else 0
        f1 = 2*p*r/(p+r) if (p+r) else 0
        g_tp += tp[t]; g_fp += fp[t]; g_fn += fn[t]
        rows.append((t, tp[t], fp[t], fn[t], round(p,3), round(r,3), round(f1,3)))
        print(f"  {t:25s}  P={p:.3f}  R={r:.3f}  F1={f1:.3f}")

    gp  = g_tp/(g_tp+g_fp) if (g_tp+g_fp) else 0
    gr  = g_tp/(g_tp+g_fn) if (g_tp+g_fn) else 0
    gf1 = 2*gp*gr/(gp+gr) if (gp+gr) else 0
    print(f"\n  GLOBAL  P={gp:.3f}  R={gr:.3f}  F1={gf1:.3f}  (= {gf1*100:.1f}%)")

    out = {"rows": rows, "global_f1": round(gf1, 4)}
    Path("docs/eval/bench_boundary_results.json").write_text(json.dumps(out, indent=2))

asyncio.run(main())
```

**Run:**
```bash
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_boundary.py
```

**Output goes to:** `content.tex` §7.2.1, Table 7.1.
Columns: Partition Type | TP | FP | FN | Precision | Recall | F1

---

### TODO-09 🟠 LLM Boundary Resolver — delta F1 (§7.2.2)
**Missing:** Table 7.2 in §7.2.2 — "LLM Fallback Contribution"
**Claim to justify:** "Fallback resolver improves F1 on ambiguous boundaries"

**File to create:** Modify `docs/eval/bench_boundary.py` — add a flag `--no-llm` that disables `LLMBoundaryResolver` and re-runs.

```bash
# Two runs:
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_boundary.py --mode deterministic-only
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_boundary.py --mode full

# Compare global F1 from both outputs → delta
```

**Output goes to:** `content.tex` §7.2.2, Table 7.2.
Columns: Mode | Global F1 | Ambiguous-boundary F1 | LLM calls made

---

## BLOCK 4 — Chapter 7: RAPTOR Ablation (§7.3)

### TODO-10 🔴 RAPTOR vs flat-index ablation — hit@5, MRR (§7.3.2)
**Missing:** Table 7.3 + Figure 7.1 in §7.3.2 — "Retrieval Quality"
**Claim to justify:** "RAPTOR hit@5 = 96.38% vs flat 84.96% → +11.42pp"
**Claim to justify:** "MRR: RAPTOR 0.91 vs flat 0.79"

**Script already exists:** `backend/scripts/ablation/run_ablation_study.py`

**Run:**
```bash
cd backend
C:/Users/labou/Desktop/Stage/venv/Scripts/python scripts/ablation/run_ablation_study.py \
    --output docs/eval/ablation_results.json
```

If the script doesn't output JSON, pipe stdout:
```bash
C:/Users/labou/Desktop/Stage/venv/Scripts/python scripts/ablation/run_ablation_study.py \
    > docs/eval/ablation_stdout.txt 2>&1
```

Then parse the output and fill Table 7.3:

| Condition | hit@1 | hit@5 | MRR | Precision@5 |
|-----------|-------|-------|-----|-------------|
| Flat LanceDB KNN | X | **84.96%** | **0.79** | X |
| RAPTOR 3-level tree | X | **96.38%** | **0.91** | X |
| Δ (RAPTOR − flat) | X | **+11.42pp** | **+0.12** | X |

Also generate a precision@k curve (k = 1..10) → Figure 7.1.

**Output goes to:** `content.tex` §7.3.2, Table 7.3 + Figure 7.1.

---

### TODO-11 🔴 RAPTOR vs flat — translation quality impact (§7.3.3)
**Missing:** Table 7.4 in §7.3.3 — "Translation Quality Impact"
**Claim to justify:** "RAPTOR advantage ≥ 10pp on MOD/HIGH partitions"

**File to create:** `docs/eval/bench_raptor_translation.py`

```python
# docs/eval/bench_raptor_translation.py
# Runs the translation pipeline on all gold-standard blocks under two conditions:
#   1. RAG = flat LanceDB KNN (bypass RAPTOR)
#   2. RAG = RAPTOR tree (normal)
# Measures syntax-valid Python success rate per condition and risk level.
# WARNING: this makes real LLM calls. Budget ~45 files × avg 10 blocks = ~450 calls.
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_raptor_translation.py

from __future__ import annotations
import asyncio, ast, json, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parents[2] / "backend"))

# You will need to patch RAGRouter to accept a force_mode="flat" or "raptor" arg.
# Add this to partition/rag/router.py:
#   def route(self, partition, force_mode=None):
#       if force_mode == "flat": return StaticRAG(...)
#       if force_mode == "raptor": # normal logic

# Then run both modes and collect results per risk level.

GOLD_DIR = Path("backend/knowledge_base/gold_standard")
results = {"flat": defaultdict(lambda: {"ok": 0, "total": 0}),
           "raptor": defaultdict(lambda: {"ok": 0, "total": 0})}

# TODO: implement pipeline run loop here using TranslationPipeline
# For each sas_file, for each block in gold.json:
#   run translate(block, rag_mode="flat")  → check ast.parse(output)
#   run translate(block, rag_mode="raptor") → check ast.parse(output)
#   record result["flat"][risk_level]["ok"] += 1 if valid

out_path = Path("docs/eval/bench_raptor_translation_results.json")
out_path.write_text(json.dumps(results, indent=2, default=dict))
```

**Output goes to:** `content.tex` §7.3.3, Table 7.4.
Columns: Risk Level | Flat success rate | RAPTOR success rate | Δ

---

### TODO-12 🟡 HyperRAPTOR pilot results (§7.3.4)
**Missing:** Table 7.5 in §7.3.4 — "HyperRAPTOR Pilot Results"

**File to create:** `docs/eval/bench_hyperraptor.py`

```bash
# Run the existing RAPTOR agent with hyperbolic embeddings enabled (geoopt must be installed)
# Compare MRR on the 50 macro-heavy gold files (gsh_* prefix) vs Euclidean RAPTOR

# Install: C:/Users/labou/Desktop/Stage/venv/Scripts/pip install geoopt
# Then run existing ablation with RAPTOR_MODE=hyperbolic env var
```

**Output goes to:** `content.tex` §7.3.4, Table 7.5.
Columns: Corpus subset | Euclidean RAPTOR MRR | HyperRAPTOR MRR | Δ

---

## BLOCK 5 — Chapter 7: Complexity Scoring (§7.4)

### TODO-13 🔴 ECE calibration curve + reliability diagram (§7.4.1)
**Missing:** Figure 7.2 + Table 7.6 in §7.4.1
**Claim to justify:** "ECE = 0.06 on held-out 20% — target < 0.08 met"

**File to create:** `docs/eval/bench_complexity_calibration.py`

```python
# docs/eval/bench_complexity_calibration.py
# Loads the trained ComplexityAgent model, runs it on held-out 20% of gold corpus,
# computes ECE and draws a reliability diagram.
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_complexity_calibration.py

from __future__ import annotations
import json, sys
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from sklearn.calibration import calibration_curve
from sklearn.metrics import log_loss

sys.path.insert(0, str(Path(__file__).parents[2] / "backend"))
from partition.complexity.complexity_agent import ComplexityAgent

GOLD_DIR = Path("backend/knowledge_base/gold_standard")

agent = ComplexityAgent()

# Load held-out 20%: sort gold files, take last 20%
gold_files = sorted(GOLD_DIR.glob("*.gold.json"))
split = int(len(gold_files) * 0.8)
held_out = gold_files[split:]

y_true, y_prob = [], []
for f in held_out:
    data = json.loads(f.read_text())
    for block in data.get("blocks", []):
        sas_src = block.get("source_code", "")
        true_risk = block.get("risk_level", "LOW")
        # Binary: HIGH/UNCERTAIN = 1, LOW/MOD = 0
        label = 1 if true_risk in ("HIGH", "UNCERTAIN") else 0
        prob = agent.predict_proba(sas_src)  # returns float in [0,1]
        y_true.append(label)
        y_prob.append(prob)

y_true = np.array(y_true)
y_prob = np.array(y_prob)

# ECE (10 equal-width bins)
n_bins = 10
bin_edges = np.linspace(0, 1, n_bins + 1)
ece = 0.0
for i in range(n_bins):
    mask = (y_prob >= bin_edges[i]) & (y_prob < bin_edges[i+1])
    if mask.sum() == 0:
        continue
    acc = y_true[mask].mean()
    conf = y_prob[mask].mean()
    ece += mask.sum() / len(y_true) * abs(acc - conf)
print(f"ECE = {ece:.4f}")

# Reliability diagram
prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=10)
fig, ax = plt.subplots(figsize=(6, 6))
ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
ax.plot(prob_pred, prob_true, "s-", label=f"ComplexityAgent (ECE={ece:.3f})")
ax.set_xlabel("Mean predicted probability"); ax.set_ylabel("Fraction of positives")
ax.set_title("Reliability Diagram — ComplexityAgent")
ax.legend(); fig.tight_layout()
Path("docs/eval/figures").mkdir(parents=True, exist_ok=True)
fig.savefig("docs/eval/figures/reliability_diagram.png", dpi=150)
print("Saved: docs/eval/figures/reliability_diagram.png")
```

**Run:**
```bash
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_complexity_calibration.py
```

**Output goes to:** `content.tex` §7.4.1, Figure 7.2 (reliability diagram) + Table 7.6 (ECE value).

---

### TODO-14 🟠 Risk distribution histogram + routing statistics (§7.4.2)
**Missing:** Figure 7.3 + Table 7.7 in §7.4.2

**File to create:** `docs/eval/bench_routing_stats.py`

```python
# docs/eval/bench_routing_stats.py
# Reads DuckDB analytics.duckdb, queries conversion_results for:
#   - risk level distribution across all translated blocks
#   - which RAG paradigm was invoked per block
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_routing_stats.py

from __future__ import annotations
import duckdb, json
from pathlib import Path

DB = Path("backend/data/analytics.duckdb")
conn = duckdb.connect(str(DB), read_only=True)

# Risk distribution
risk_dist = conn.execute("""
    SELECT metadata->>'risk_level' as risk, COUNT(*) as cnt
    FROM conversion_results
    GROUP BY 1 ORDER BY cnt DESC
""").fetchall()
print("Risk distribution:", risk_dist)

# RAG paradigm usage
rag_usage = conn.execute("""
    SELECT metadata->>'rag_paradigm' as paradigm, COUNT(*) as cnt
    FROM conversion_results
    GROUP BY 1 ORDER BY cnt DESC
""").fetchall()
print("RAG paradigm usage:", rag_usage)

# LLM tier usage
tier_usage = conn.execute("""
    SELECT model_used, COUNT(*) as cnt
    FROM conversion_results
    GROUP BY model_used ORDER BY cnt DESC
""").fetchall()
print("LLM tier usage:", tier_usage)

conn.close()
```

**Run:**
```bash
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_routing_stats.py
```

**Output goes to:** `content.tex` §7.4.2, Figure 7.3 (bar chart) + Table 7.7 (RAG paradigm invocation counts).

---

## BLOCK 6 — Chapter 7: Translation Results (§7.5)

### TODO-15 🔴 End-to-end translation success rate by risk level + partition type (§7.5.1)
**Missing:** Table 7.8 in §7.5.1
**Claim to justify:** "70% end-to-end translation success rate"

**File to create:** `docs/eval/bench_translation_success.py`

```python
# docs/eval/bench_translation_success.py
# Reads all conversion_results rows from DuckDB and computes:
#   - overall syntax-valid success rate
#   - breakdown by risk_level
#   - breakdown by partition_type
# Assumes pipeline has already been run on the 45 gold-standard files.
# If not: first run backend/scripts/eval/translate_test.py on all gold files.
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_translation_success.py

from __future__ import annotations
import duckdb, json
from pathlib import Path
from collections import defaultdict

DB = Path("backend/data/analytics.duckdb")
conn = duckdb.connect(str(DB), read_only=True)

rows = conn.execute("""
    SELECT status, metadata->>'risk_level' as risk,
           metadata->>'partition_type' as ptype
    FROM conversion_results
""").fetchall()
conn.close()

total = len(rows)
ok = sum(1 for r in rows if r[0] == "completed")
print(f"Overall: {ok}/{total} = {ok/total*100:.1f}%")

by_risk = defaultdict(lambda: [0, 0])
by_type = defaultdict(lambda: [0, 0])
for status, risk, ptype in rows:
    by_risk[risk][1] += 1
    by_type[ptype][1] += 1
    if status == "completed":
        by_risk[risk][0] += 1
        by_type[ptype][0] += 1

print("\nBy risk level:")
for k, (ok, total) in sorted(by_risk.items()):
    print(f"  {k}: {ok}/{total} = {ok/total*100:.1f}%")

print("\nBy partition type:")
for k, (ok, total) in sorted(by_type.items()):
    print(f"  {k}: {ok}/{total} = {ok/total*100:.1f}%")
```

**Run (two-step):**
```bash
# Step 1: run pipeline on all 45 gold files (if not done yet)
cd backend
C:/Users/labou/Desktop/Stage/venv/Scripts/python scripts/eval/translate_test.py \
    --input knowledge_base/gold_standard --all

# Step 2: query results
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_translation_success.py
```

**Output goes to:** `content.tex` §7.5.1, Table 7.8.
Columns: Risk Level | Blocks | Completed | Success Rate (%)

---

### TODO-16 🔴 Z3 verification outcomes — counterexamples + CEGAR repairs (§7.5.2)
**Missing:** Table 7.9 + Table 7.10 in §7.5.2

**File to create:** `docs/eval/bench_z3_outcomes.py`

```python
# docs/eval/bench_z3_outcomes.py
# Queries DuckDB for Z3 verification outcomes across all completed HIGH/UNCERTAIN blocks.
# Reports: blocks submitted, verified OK, counterexample found, CEGAR repairs, final verified.
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_z3_outcomes.py

from __future__ import annotations
import duckdb
from pathlib import Path

DB = Path("backend/data/analytics.duckdb")
conn = duckdb.connect(str(DB), read_only=True)

outcomes = conn.execute("""
    SELECT
        metadata->>'z3_outcome'       as outcome,
        metadata->>'z3_pattern'       as pattern,
        metadata->>'cegar_iterations' as cegar_iters,
        COUNT(*) as cnt
    FROM conversion_results
    WHERE metadata->>'z3_submitted' = 'true'
    GROUP BY 1, 2, 3
    ORDER BY cnt DESC
""").fetchall()

for row in outcomes:
    print(row)
conn.close()
```

**Output goes to:** `content.tex` §7.5.2, Table 7.9 (outcome counts) + Table 7.10 (pattern-level breakdown).

---

### TODO-17 🟠 Failure mode distribution (§7.5.3)
**Missing:** Table 7.11 in §7.5.3 — top 3 failure modes by frequency

**File to create:** `docs/eval/bench_failure_modes.py`

```python
# docs/eval/bench_failure_modes.py
import duckdb
from pathlib import Path
from collections import Counter

DB = Path("backend/data/analytics.duckdb")
conn = duckdb.connect(str(DB), read_only=True)

rows = conn.execute("""
    SELECT metadata->>'failure_mode' as fm, COUNT(*) as cnt
    FROM conversion_results
    WHERE status != 'completed'
    GROUP BY 1 ORDER BY cnt DESC
""").fetchall()
conn.close()

total_failed = sum(r[1] for r in rows)
for fm, cnt in rows:
    print(f"  {fm}: {cnt} ({cnt/total_failed*100:.1f}%)")
```

**Output goes to:** `content.tex` §7.5.3, Table 7.11.
Columns: Failure Mode | Count | % of failures | Implication for KB expansion

---

### TODO-18 🔴 Streaming performance — time + peak RSS on 10K-line file (§7.5.4)
**Missing:** Table 7.12 in §7.5.4
**Claim to justify:** "10K-line SAS file processed < 2s, < 100MB peak RSS"

**File to create:** `docs/eval/bench_streaming.py`

```python
# docs/eval/bench_streaming.py
# Benchmarks the streaming pipeline (L2-B) on files of varying sizes.
# Measures wall time and peak RSS memory.
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_streaming.py

from __future__ import annotations
import asyncio, time, tracemalloc, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "backend"))
from partition.streaming.pipeline import run_streaming_pipeline

# Generate synthetic SAS files of 1K, 5K, 10K, 20K lines
def make_sas(n_lines: int) -> str:
    lines = []
    for i in range(0, n_lines, 10):
        lines += [
            f"data work.test{i};",
            f"  set work.input{i};",
            f"  if x > {i} then y = x * 2;",
            f"  retain total 0;",
            f"  total + x;",
            f"run;",
            "",
            f"proc means data=work.test{i};",
            f"  var x y;",
            "run;",
        ]
    return "\n".join(lines[:n_lines])

async def bench(n_lines: int):
    sas = make_sas(n_lines)
    tracemalloc.start()
    t0 = time.perf_counter()
    await run_streaming_pipeline(sas)
    elapsed = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print(f"  {n_lines:6d} lines | {elapsed:.2f}s | peak RSS {peak/1024/1024:.1f} MB")

async def main():
    for n in [1_000, 5_000, 10_000, 20_000]:
        await bench(n)

asyncio.run(main())
```

**Run:**
```bash
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_streaming.py
```

**Output goes to:** `content.tex` §7.5.4, Table 7.12.
Columns: File size (lines) | Wall time (s) | Peak RSS (MB) | NFR-01 met?

---

## BLOCK 7 — Chapter 7: System Performance (§7.6)

### TODO-19 🟠 API latency p50/p95 by complexity tier (§7.6.1)
**Missing:** Table 7.13 in §7.6.1

**File to create:** `docs/eval/bench_api_latency.py`

```python
# docs/eval/bench_api_latency.py
# Sends real API requests (upload → start → poll until done) for files from each
# complexity tier. Measures total wall time and polls latency.
# Requires: API running on localhost:8000
# Run: C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_api_latency.py

from __future__ import annotations
import time, requests, json, numpy as np
from pathlib import Path

BASE = "http://localhost:8000/api"
TOKEN = json.loads(requests.post(f"{BASE}/auth/login",
    json={"email": "user@codara.dev", "password": "user123!"}).text)["access_token"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

GOLD_DIR = Path("backend/knowledge_base/gold_standard")
TIER_FILES = {
    "LOW":  sorted(GOLD_DIR.glob("gs_*.sas"))[:5],     # basic files
    "MOD":  sorted(GOLD_DIR.glob("gsm_*.sas"))[:5],    # medium files
    "HIGH": sorted(GOLD_DIR.glob("gsh_*.sas"))[:5],    # hard files
}

for tier, files in TIER_FILES.items():
    times = []
    for f in files:
        # Upload
        with open(f, "rb") as fp:
            up = requests.post(f"{BASE}/conversions/upload",
                headers=HEADERS, files={"files": (f.name, fp, "text/plain")})
        file_id = up.json()[0]["id"]

        # Start
        start = requests.post(f"{BASE}/conversions/start",
            headers=HEADERS, json={"file_ids": [file_id], "runtime": "python"})
        conv_id = start.json()["id"]

        # Poll until done
        t0 = time.perf_counter()
        while True:
            status = requests.get(f"{BASE}/conversions/{conv_id}", headers=HEADERS).json()["status"]
            if status in ("completed", "failed", "partial"):
                break
            time.sleep(1.0)
        times.append(time.perf_counter() - t0)

    p50 = np.percentile(times, 50)
    p95 = np.percentile(times, 95)
    print(f"  {tier}: p50={p50:.1f}s  p95={p95:.1f}s  (n={len(times)})")
```

**Run (API must be running):**
```bash
# Terminal 1: start API
cd backend && C:/Users/labou/Desktop/Stage/venv/Scripts/python -m uvicorn api.main:app --port 8000

# Terminal 2: run benchmark
C:/Users/labou/Desktop/Stage/venv/Scripts/python docs/eval/bench_api_latency.py
```

**Output goes to:** `content.tex` §7.6.1, Table 7.13.
Columns: Complexity Tier | n | p50 latency (s) | p95 latency (s)

---

### TODO-20 🟠 LLM token cost analysis from DuckDB (§7.6.2)
**Missing:** Table 7.14 in §7.6.2

**File to create:** `docs/eval/bench_llm_cost.py`

```python
# docs/eval/bench_llm_cost.py
import duckdb
from pathlib import Path

DB = Path("backend/data/analytics.duckdb")
conn = duckdb.connect(str(DB), read_only=True)

stats = conn.execute("""
    SELECT
        model_used,
        COUNT(*)              as calls,
        AVG(prompt_tokens)    as avg_prompt_tokens,
        AVG(completion_tokens) as avg_completion_tokens,
        SUM(cost_usd)         as total_cost_usd
    FROM llm_calls
    GROUP BY model_used
    ORDER BY calls DESC
""").fetchall()
conn.close()

for row in stats:
    print(row)
```

**Output goes to:** `content.tex` §7.6.2, Table 7.14.
Columns: Model | Calls | Avg prompt tokens | Avg completion tokens | Total cost (USD)

---

### TODO-21 🔴 Test suite coverage report (§7.6.3)
**Missing:** Table 7.15 in §7.6.3
**Claim to justify:** "248 tests, ≥80% coverage"

**Run:**
```bash
cd backend
C:/Users/labou/Desktop/Stage/venv/Scripts/python -m pytest tests/ \
    --cov=partition --cov=api \
    --cov-report=term-missing \
    --cov-report=html:../docs/eval/coverage_html \
    --tb=short -q \
    > ../docs/eval/coverage_report.txt 2>&1
```

Then open `docs/eval/coverage_html/index.html` and extract the per-module table.

**Output goes to:** `content.tex` §7.6.3, Table 7.15.
Columns: Module | Statements | Missing | Coverage %

---

## BLOCK 8 — Chapter 7: Related Work Comparison (§7.8)

### TODO-22 🟠 Codara vs related work — 6-dimension table (§7.8.2)
**Missing:** Table 7.16 in §7.8.2 — "Comparison with Academic Code Translation Approaches"

**File to create:** `docs/eval/comparison_related_work.md`

Build from literature:

| System | Year | SAS Support | Semantic Verification | RAG | Multi-agent | Open Source |
|--------|------|-------------|----------------------|-----|-------------|-------------|
| TransCoder (Rozière et al.) | 2020 | ✗ | ✗ | ✗ | ✗ | ✓ |
| CodeT5 (Wang et al.) | 2021 | Partial | ✗ | ✗ | ✗ | ✓ |
| SAS Migration Accelerator | 2022 | ✓ | ✗ | ✗ | ✗ | ✗ |
| GPT-4 zero-shot | 2023 | Partial | ✗ | ✗ | ✗ | ✗ |
| MultiAgent-CoT (Chen et al.) | 2023 | ✗ | ✗ | ✓ | ✓ | ✗ |
| **Codara (this work)** | 2026 | ✓ Full | ✓ Z3 SMT | ✓ 3-tier RAPTOR | ✓ 8-node | ✓ |

**Output goes to:** `content.tex` §7.8.2, Table 7.16.

---

## SUMMARY CHECKLIST

| # | Script / file | Run command | Thesis location | Status |
|---|---------------|-------------|-----------------|--------|
| 01 | `docs/eval/tool_comparison.md` | manual | §1.4.2 Table 1.1 | ⬜ |
| 02 | `docs/eval/methodology_comparison.md` | manual | §1.5.5 Table 1.2 | ⬜ |
| 03 | `docs/eval/bench_orchestration.md` + timing script | `python bench_orchestration_timing.py` | §4.2.1 Table 4.1 | ⬜ |
| 04 | `docs/eval/bench_llm_models.py` | `python bench_llm_models.py` | §4.2.2 Table 4.2 | ⬜ |
| 05 | `docs/eval/bench_embeddings.py` | `python bench_embeddings.py` | §4.2.3 Table 4.3 | ⬜ |
| 06 | `docs/eval/bench_smt_solvers.md` | manual | §4.2.4 Table 4.4 | ⬜ |
| 07 | `docs/eval/corpus_stats.py` | `python corpus_stats.py` | §4.5.4 Table 4.5 + Fig 4.1 | ⬜ |
| 08 | `docs/eval/bench_boundary.py` | `python bench_boundary.py` | §7.2.1 Table 7.1 | ⬜ |
| 09 | `docs/eval/bench_boundary.py --mode` | two runs | §7.2.2 Table 7.2 | ⬜ |
| 10 | `backend/scripts/ablation/run_ablation_study.py` | existing script | §7.3.2 Table 7.3 + Fig 7.1 | ⬜ |
| 11 | `docs/eval/bench_raptor_translation.py` | `python bench_raptor_translation.py` | §7.3.3 Table 7.4 | ⬜ |
| 12 | `docs/eval/bench_hyperraptor.py` | `python bench_hyperraptor.py` | §7.3.4 Table 7.5 | ⬜ |
| 13 | `docs/eval/bench_complexity_calibration.py` | `python bench_complexity_calibration.py` | §7.4.1 Fig 7.2 + Table 7.6 | ⬜ |
| 14 | `docs/eval/bench_routing_stats.py` | `python bench_routing_stats.py` | §7.4.2 Fig 7.3 + Table 7.7 | ⬜ |
| 15 | `docs/eval/bench_translation_success.py` | 2-step (translate then query) | §7.5.1 Table 7.8 | ⬜ |
| 16 | `docs/eval/bench_z3_outcomes.py` | `python bench_z3_outcomes.py` | §7.5.2 Table 7.9 + 7.10 | ⬜ |
| 17 | `docs/eval/bench_failure_modes.py` | `python bench_failure_modes.py` | §7.5.3 Table 7.11 | ⬜ |
| 18 | `docs/eval/bench_streaming.py` | `python bench_streaming.py` | §7.5.4 Table 7.12 | ⬜ |
| 19 | `docs/eval/bench_api_latency.py` | API running + `python bench_api_latency.py` | §7.6.1 Table 7.13 | ⬜ |
| 20 | `docs/eval/bench_llm_cost.py` | `python bench_llm_cost.py` | §7.6.2 Table 7.14 | ⬜ |
| 21 | `pytest --cov` | run in `backend/` | §7.6.3 Table 7.15 | ⬜ |
| 22 | `docs/eval/comparison_related_work.md` | manual | §7.8.2 Table 7.16 | ⬜ |

---

## ORDER OF EXECUTION (least LLM-cost first)

1. **TODO-07** corpus_stats.py — free, 2 min
2. **TODO-21** pytest coverage — free, 5 min
3. **TODO-08/09** bench_boundary.py — free (no LLM if deterministic-only first), 10 min
4. **TODO-13** bench_complexity_calibration.py — free (reads trained model), 5 min
5. **TODO-14** bench_routing_stats.py — free (reads DuckDB), 2 min
6. **TODO-18** bench_streaming.py — free (no LLM), 5 min
7. **TODO-20** bench_llm_cost.py — free (reads DuckDB), 2 min
8. **TODO-10** run_ablation_study.py — uses embeddings (no LLM), 20 min
9. **TODO-05** bench_embeddings.py — uses sentence-transformers (no LLM), 15 min
10. **TODO-03** bench_orchestration_timing.py — no LLM, 5 min
11. **TODO-04** bench_llm_models.py — uses LLM (torture test only, ~50 calls), 30 min
12. **TODO-15** bench_translation_success.py — most expensive (~450 LLM calls), save for last
13. **TODO-16/17** bench_z3_outcomes.py / bench_failure_modes.py — reads results from above, free
14. **TODO-11** bench_raptor_translation.py — expensive (needs step 12 done first)
15. **TODO-19** bench_api_latency.py — end-to-end, needs API + LLM running
