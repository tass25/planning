# Codara — Evaluation Metrics Reference

All metrics, targets, and justifications in one place.

---

## Retrieval Quality (RAG / RAPTOR)

| Metric | Definition | Target | Justification |
|--------|-----------|--------|---------------|
| **hit@5** | Fraction of queries where the correct KB example appears in the top-5 results | > 0.82 | Below 0.82 the translation prompt rarely sees relevant examples, causing hallucinated patterns. Empirically derived from Week 12 ablation (flat baseline was 0.89). |
| **MRR** (Mean Reciprocal Rank) | Average of 1/rank for the first correct result | > 0.60 | MRR < 0.60 means the correct example is typically at rank 2+, diluting prompt context. |
| **RAPTOR advantage (MOD/HIGH)** | Weighted hit@5 delta between RAPTOR and flat index on MODERATE+HIGH partitions | ≥ 10 pp | Validates that hierarchical clustering adds value for complex code. If < 10 pp, the RAPTOR overhead is not justified. |
| **Query latency** | Wall-clock time per retrieval query (embedding + search) | < 50 ms | Must be negligible vs LLM call latency (~5-15s). |

### Achieved (Ablation Run 2026-04-01)

| Metric | Flat | RAPTOR | Delta |
|--------|------|--------|-------|
| hit@5 | 0.8948 | **0.9638** | +6.90 pp |
| MRR | 0.8737 | **0.9427** | +6.90 pp |
| MOD/HIGH advantage (weighted) | — | — | **+11.42 pp** |
| Query latency | 5.5 ms | 8.3 ms | +2.8 ms |

---

## Translation Quality

| Metric | Definition | Target | Justification |
|--------|-----------|--------|---------------|
| **Success rate** | Fraction of blocks with status=SUCCESS (syntax valid + exec pass) | ≥ 70% | Remaining 30% expected for advanced SAS idioms (RETAIN, hash, macros). |
| **Syntax validity** | Fraction of translations that pass `ast.parse()` | ≥ 95% | Syntax errors indicate prompt failures, not semantic difficulty. |
| **LLM confidence** | Self-reported confidence from structured output (0-1) | ≥ 0.85 mean | Calibrated against actual success — below 0.85 triggers cross-verify. |
| **Cross-verify agreement** | Fraction where primary and verifier produce equivalent output | Informational | No target — used for flagging, not filtering. |

### Achieved (Model Benchmark 2026-04-15, torture_test.sas)

| Model | Success | Syntax valid | Mean confidence | Z3 proved |
|-------|---------|-------------|-----------------|-----------|
| minimax-m2.7:cloud | 100% | 100% | 0.94 | 3/10 |
| nemotron-3-super:cloud | 100% | 100% | 0.93 | 3/10 |
| qwen3-coder-next | 0% | 0% | 0.00 | 0/10 |
| deepseek-v3.2 | 0% | 0% | 0.00 | 0/10 |

---

## Formal Verification (Z3)

| Metric | Definition | Target | Justification |
|--------|-----------|--------|---------------|
| **Proved rate** | Fraction of blocks where Z3 formally proves semantic equivalence | ≥ 25% | Z3 covers 4 decidable patterns (linear arithmetic, boolean filter, sort/dedup, assignment). ~70% of SAS idioms are outside this fragment. |
| **Counterexample rate** | Fraction where Z3 finds a concrete divergence | 0% | Any counterexample means a translation bug — must be 0% for shipped translations. |
| **Z3 latency** | Mean solver time per block | < 50 ms | Must not bottleneck pipeline. |

### Achieved (Z3 Audit 2026-04-10)

| Metric | Value |
|--------|-------|
| Proved | 3/10 (30%) |
| Counterexamples | 0/10 (0%) |
| Unknown (out of scope) | 7/10 (70%) |
| Mean latency | 4.6 ms |

---

## Pipeline Performance

| Metric | Definition | Target | Justification |
|--------|-----------|--------|---------------|
| **Streaming throughput** | Lines/second for FSM parsing | > 5,000 lines/s | 10K-line file must parse in < 2s. |
| **Peak memory** | Max RSS during pipeline run | < 100 MB (10K-line file) | Must run on CI runners (2 GB) and dev laptops. |
| **Boundary accuracy** | Fraction of correctly detected block boundaries on gold corpus | > 90% | Below 90%, downstream translation sees broken partitions. |
| **Complexity ECE** | Expected Calibration Error of ComplexityAgent ML model | < 0.08 | Miscalibrated risk scores misroute partitions (e.g., LOW→StaticRAG for a HIGH block). |
| **End-to-end latency** | Total wall-clock time for a 10-block file | < 5 min | Practical for interactive use. |

---

## CDAIS (Constraint-Driven Adversarial Input Synthesis)

| Metric | Definition | Target | Justification |
|--------|-----------|--------|---------------|
| **Detection rate** | Error classes detected deterministically | 5/6 | C3 (SORT_STABLE) requires non-deterministic quicksort witness. |
| **Witness size** | Number of rows in minimal adversarial input | 3-6 rows | Small witnesses make counterexamples interpretable. |
| **Synthesis time** | Z3 solver time for constraint satisfaction | < 100 ms | Must be fast enough for CI integration. |
| **Oracle pass rate** | Fraction of MIS invariants that pass on verified corpus | 100% | False positives in invariants would cause spurious test failures. |

### Achieved

| Metric | Value |
|--------|-------|
| Detection rate | 5/6 (83.3%) |
| Witness size | 3-6 rows |
| Synthesis time | ~42 ms mean |
| Oracle pass rate | 100% (12-pair verified corpus) |

---

## Knowledge Base

| Metric | Definition | Target | Justification |
|--------|-----------|--------|---------------|
| **Total pairs** | Verified SAS→Python examples in LanceDB | ≥ 330 (current), 380 (stretch) | Below 300, retrieval quality degrades on rare partition types. |
| **Category coverage** | Number of distinct categories with ≥ 5 pairs | ≥ 15 | Sparse categories produce poor few-shot examples. |
| **Verified ratio** | Fraction of pairs with `verified=True` | ≥ 90% | Unverified pairs may contain errors that propagate to translations. |

---

## Cost Estimation

| Model | Input (per 1M tokens) | Output (per 1M tokens) | Source |
|-------|----------------------|------------------------|--------|
| minimax-m2.7:cloud (Ollama) | $0.00 | $0.00 | Self-hosted / free tier |
| GPT-5.4-mini (Azure) | $2.50 | $10.00 | Azure pricing 2026-04 |
| GPT-5.4-mini-mini (Azure) | $0.15 | $0.60 | Azure pricing 2026-04 |
| LLaMA-3.3-70B (Groq) | $0.00 | $0.00 | Free tier (100K TPD/key) |

Typical 10-block conversion cost: ~$0.01-0.03 (Azure), $0.00 (Ollama/Groq free tier).
