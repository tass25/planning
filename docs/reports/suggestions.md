# Codara — Audit Report & Research Roadmap
*Audit: 2026-04-10 · Research plan: April 2026*

---

## Part 1 — Full Project Audit

**Audited by:** 5-agent parallel review team + synthesizer

### Scorecard

| Area | Score | Grade |
|---|---|---|
| Architecture | 7.5 / 10 | B+ |
| Code Quality | 6.5 / 10 | B- |
| Security | 3.0 / 10 | F |
| Completeness | 4.0 / 10 | D |
| Test Coverage | 7.2 / 10 | B |
| **Overall** | **5.6 / 10** | **C+** |

---

### Top 5 Critical Issues

#### 🔴 #1 — Real API Keys Committed to `.env` (Security · CRITICAL)
`.env` contains live, production secrets in plaintext:
- Azure OpenAI key, GitHub OAuth secret, JWT signing secret
- 6× NVIDIA API keys, 3× Groq keys, Gemini key, Ollama key

**Action:** Rotate ALL keys immediately. Use Azure Key Vault or pre-commit hook to block `.env` from ever being staged.

---

#### 🔴 #2 — Pipeline Stages 5–8 Are Fake (Completeness · CRITICAL)
`_run_pipeline_sync()` executes real agents only for stages 1–4. Stages 5–8 are `time.sleep()` placeholders. `conv.python_code` remains `null`. The core product does not work end-to-end via the API.

**Action:** Wire `TranslationPipeline.translate_partition()` into `_run_pipeline_sync()`, remove all fake sleep stages.

---

#### 🔴 #3 — Three Core Paper Contributions Are Missing (Completeness · CRITICAL)

| Contribution | Status |
|---|---|
| Oracle Verification Agent | ❌ Not implemented |
| Best-of-N Translator | ❌ Not implemented |
| Adversarial Pipeline (Proposer→Critic→Refiner) | ❌ Not implemented |

5+ ablation scripts referenced in ROADMAP also do not exist.

---

#### 🟠 #4 — Z3 Agent Exists but Is Never Called (Architecture · HIGH)
`Z3VerificationAgent` has 8 patterns and 16 passing tests but is not wired into `TranslationPipeline`. See Research Idea #2 below.

---

#### 🟠 #5 — Hardcoded Default Credentials (Security · HIGH)
`main.py` auto-creates `admin123!` / `user123!` accounts unconditionally on every DB init.

**Action:** Remove seed credentials. Generate random password at first boot or require env var.

---

### Full Findings by Area

#### Architecture — 7.5/10
**Strengths:** Clear 8-stage LangGraph orchestration, clean api/partition separation, conftest.py prevents test DB pollution.

**Weaknesses:**
- `TranslationPipeline` directly instantiates all sub-agents — no DI
- Two database layers with no shared transaction management
- `PartitionIR.metadata` dict mutated by multiple agents with no schema
- `RAGRouter` shares a single mutable `KBQueryClient` across all RAG paradigms
- `UPLOAD_DIR` hardcoded relative to `api/main.py` — breaks if package moves

#### Code Quality — 6.5/10
- `conversions.py:43,66,253` — bare `except Exception: pass` silently swallows errors
- `_translate_azure_4o()` and `_translate_azure_mini()` are 95% identical — merge into `_translate_with_tier(tier)`
- `translate_partition()` is 110 lines, 5+ nesting levels
- `asyncio.to_thread()` at line 353 has no timeout — can hang indefinitely
- `resp.choices[0].message.content` at line 296 — no guard against empty `choices`

#### Security — 3/10
**CRITICAL:** Live keys in `.env`, default passwords, upload only checks `.sas` extension (no size limit, no MIME validation).
**MEDIUM:** No rate limiting on `/login`/`/signup`, email verification stub, CORS hardcoded to localhost.
**LOW:** JWT in `localStorage` (XSS-accessible), no HTTPS enforcement, filenames unsanitized in DB.
**Passed:** SQLAlchemy parameterized queries, bcrypt hashing.

#### Completeness — 4/10
Pipeline stages 5–8 fake, Oracle Agent missing, Best-of-N missing, Adversarial Pipeline missing, Z3 not wired, 5+ ablation scripts missing.

#### Test Coverage — 7.2/10
**Zero tests for:** all 11 API route files, `api/auth.py`, `llm_clients.py`, `config_manager.py`, entire `retraining/` module.
**Test quality issues:** hardcoded Windows path in `test_streaming.py:308`, bare `except` in test bodies, no Azure/Groq mocks (CI requires real keys).

---

### Action Plan

| Week | Actions |
|------|---------|
| 1 | Rotate all keys · Remove seed credentials · Wire TranslationPipeline into API · Wire Z3 + CEGAR |
| 2 | Best-of-N Translator · Oracle Verification Agent · Ablation scripts |
| 3 | Rate limiting · File size validation · Deduplicate LLM fallback · Split large functions |
| 4 | API route tests · Mock Azure/Groq in CI · Adversarial pipeline · Fix Windows paths |

---

## Part 2 — Research Ideas for Publication

**Removed permanently:** zkML certificates (ZK-SNARK needs GPU cluster), Quantum QUBO on D-Wave (commercial hardware), Federated KB (no institutional clients), Real-time collaboration (wrong problem), PRM as originally described (no process labels), Self-evolving agent (undefined mechanism), Online DVI training (no GPU for backward pass).

---

### The Ideas Worth Building

| # | Idea | What's actually new | What you build | Innovation | Feasibility | Conference |
|---|------|---------------------|----------------|-----------|-------------|------------|
| **P1** | **Execution-Grounded Prompting** | Every migration tool prompts on SAS syntax. Nobody shows the LLM what the code *does* before asking it to translate. SAS is underrepresented in all pretraining corpora — showing behavior examples (input dataset → output dataset) resolves semantic ambiguity Z3 and syntax checks cannot. | SAS DATA step micro-interpreter (~200 lines Python, PDV model). Generate 3 synthetic input/output pairs per partition. Inject into prompt before translation call. Ablate on 45 gold pairs: with vs. without examples, measured by Z3 verification rate and syntax validity. | ⭐⭐⭐⭐⭐ | ✅ Zero paid APIs | **ASE 2026 / ICSE 2026** |
| **P2** | **Three-Tier Verification Hierarchy** | Z3 is sound but covers 8 patterns (no floats, strings, macros). Execution testing is complete but not sound. Reasoning models (DeepSeek-R1-Distill-32B, free via Ollama) can reason about equivalence for patterns neither Z3 nor execution handles — and their chain-of-thought is the certificate. Nobody has characterized when thinking-model traces can substitute formal proofs in code migration. | Pull DeepSeek-R1-Distill-32B via Ollama. Post-hoc: given SAS + Python translation, ask reasoning model to check equivalence step by step. Extract verdict from `<think>` trace. Measure: Z3 catches X errors on torture test, execution catches Y, reasoning model catches Z. Venn diagram of coverage is the main figure. | ⭐⭐⭐⭐⭐ | ✅ Ollama only | **ASE 2026 / ISSTA 2026** |
| **P3** | **DPO with Z3 as Formal Reward** | Every DPO/RLHF paper for code uses human judges or test execution pass/fail. You have a formal proof engine. Z3 PROVED = preferred translation, Z3 COUNTEREXAMPLE = rejected. This makes Z3 an automated, zero-human preference oracle — unprecedented in code migration alignment. | For each of 330 KB pairs, generate 3-5 wrong translations (Groq, temp=1.0, inject known failure modes). Run Z3 on all pairs. Build (correct, wrong) preference dataset. DPO fine-tune Qwen2.5-Coder-7B with HuggingFace `trl` on Colab T4. Measure Z3 counterexample rate on held-out 50 gold pairs: base model vs. DPO-aligned. | ⭐⭐⭐⭐⭐ | ✅ Colab T4 free | **NeurIPS 2026 / ACL 2026** |
| **P4** | **Does the Pipeline Still Make Sense?** | Codara's 8-node pipeline (chunking, RAPTOR, boundary detection) was designed for 4K-context models. In 2025, Qwen2.5-72B has 128K context and minimax-M1 has 1M. Nobody has empirically tested whether chunk-by-chunk translation still beats a single whole-program prompt. If it does, why? If it doesn't, the entire 2022-2024 migration pipeline architecture is obsolete. | Take 45 gold programs. Run: (A) full Codara pipeline, (B) single prompt to Qwen2.5-72B with entire file, (C) hybrid — long context translation + Z3 per block. Compare accuracy, latency, Z3 rate, cross-reference handling. Find the crossover program size where pipeline wins vs. loses. | ⭐⭐⭐⭐⭐ | ✅ Azure OpenAI credits | **ICSE 2026 / FSE 2026** |
| **P5** | **Formal Complexity → Inference Budget** | "Retry twice on failure" is an arbitrary heuristic. Your ComplexityAgent already produces a calibrated risk score. Use it to allocate inference compute *before* the first attempt: LOW = 1 sample, MOD = best-of-3, HIGH = best-of-8 with Z3 verifier selecting the winner. Nobody has used a formal complexity estimate to drive test-time compute allocation. | Wire ComplexityAgent score into a budget scheduler that controls number of translation samples per partition. Implement best-of-N selection using Z3 as the verifier. Ablate: fixed 2-retry budget vs. complexity-adaptive budget at equal total LLM call count. Metric: Z3 verification rate per 100 LLM calls. | ⭐⭐⭐⭐ | ✅ Zero new infra | **ASE 2026 / ICSE 2026** |
| **P6** | **Automatic Z3 Pattern Discovery via Specification Mining** | You have 330 verified SAS→Python pairs. Each pair is an implicit invariant: when pattern X appears in SAS, structure Y must appear in Python. Run a decision tree over execution trace features extracted by the emulator. Mined invariants become new Z3 patterns automatically — no hand-engineering. This grows your formal verification coverage from 8 patterns without writing Z3 encoders. | Build emulator (P1 prerequisite). For each KB pair run on synthetic data, record trace features (variables retained, conditions evaluated, output schema). Train decision tree (scikit-learn) to classify correct vs. wrong translations. Extract rules as Z3 assertions. Validate: does mining rediscover the 8 existing patterns? Does it find new ones? | ⭐⭐⭐⭐ | ✅ scikit-learn only | **ISSTA 2026 / ASE 2026** |
| **P7** | **Synthetic SAS Generation with Dual-Filter** | Use LLM to mutate 45 gold pairs into thousands of synthetic SAS programs. Filter with Z3 (formal, 8 patterns) AND execution emulator (empirical, all patterns). Two independent verification channels is the contribution — no other code migration KB construction paper uses a formal verifier as a data quality filter. Scale KB from 330 to 10K+ verifiably correct pairs. | Build emulator. Prompt Groq to mutate each gold pair (increase nesting, add edge cases, combine patterns). For each generated pair: run Z3, run emulator on 50 random input DataFrames, compare outputs. Accept only pairs that pass both. Measure final KB size, Z3 coverage, emulator coverage. | ⭐⭐⭐⭐ | ✅ Groq free tier | **MSR 2026 / ASE 2026** |
| **P8** | **QUBO Formulation for Partition Boundary Optimization** (no quantum) | Boundary detection is currently heuristic (Lark grammar + LLM fallback). Formulate it as a QUBO: binary variable per potential split point, objective minimizes translation coupling complexity across partitions. Solve with OR-Tools (free, Google) or scipy simulated annealing. The contribution is the formal objective function, not the solver. This is the innovation from the quantum idea without the infeasible hardware. | Define QUBO objective: sum of cross-partition dependency weights. Solve with OR-Tools CP-SAT. Compare boundary accuracy vs. current deterministic detector on 721-block gold corpus. Ablate: does formal boundary optimization improve downstream translation Z3 rate? | ⭐⭐⭐⭐ | ✅ OR-Tools free | **ASE 2026 / CGO 2026** |

---

### Supporting Ideas (build these to enable the papers above, not standalone publications)

| # | Idea | Why you need it | Effort |
|---|------|----------------|--------|
| **S0** | **SAS DATA Step Emulator** | Prerequisite for P1, P2, P6, P7. ~200 lines Python: PDV model, RETAIN, IF/THEN, SET, FIRST./LAST. | 1 week |
| **S1** | **Wire Z3 + CEGAR into TranslationPipeline** | Already built, not wired. Required for every paper's baseline. | 1 day |
| **S2** | **Z3 pattern extension (8 → 12+)** | Add RETAIN, hash objects, macro expansion patterns to Z3. Directly extends P2 coverage. | 3 days |
| **S3** | **Contextual bandit KB weighting** | When translation fails, decrease retrieval weight of used examples (Thompson sampling, 50 lines numpy). Measurable improvement to retrieval quality. | 2 days |
| **S4** | **Schema-constrained generation** | Extend `TranslationOutput` Pydantic model to enforce structural invariants per PROC type (PROC MEANS → must contain groupby). Uses existing instructor integration. | 2 days |
| **S5** | **Static speculative translation** | Small GGUF drafter + Z3 accept/reject gate. No backward pass. 3× speedup on LOW-risk blocks. | 1 week |
| **S6** | **LLM-generated SMT in restricted sublanguage** | LLM generates Z3 formulas only for integer/real arithmetic DATA steps (sound by construction in that sublanguage). Extends P2 coverage. | 1 week |

---

### Product Features (demo value, not publications)

| # | Feature | Verdict | Effort |
|---|---------|---------|--------|
| **F1** | Wire Z3 + CEGAR, document repair rate | IMPLEMENT NOW — already built, measure it | 1 day |
| **F2** | Conversion diff UI (react-diff-viewer + /corrections) | IMPLEMENT NOW — 2 days, high demo value | 2 days |
| **F3** | KB auto-expansion via correction loop | IMPLEMENT NOW — FeedbackIngestionAgent exists, wire Z3 into it | 1 day |
| **F4** | DuckDB analytics dashboard (3 recharts cards) | IMPLEMENT NOW — tables already populated | 1 day |
| **F5** | CI benchmark regression (translate_test.py gated) | IMPLEMENT NOW — prevents silent quality regression | 1 day |
| **F6** | QLoRA fine-tuning (after KB hits 380+ pairs) | IMPLEMENT LATER — run on Colab T4 after data is ready | 4-8h GPU |
| **F7** | LocalModel Tier 0 (wire local_model_client.py) | IMPLEMENT LATER — already written | 1 day |
| **F8** | PySpark output (Jinja2 templates + validation) | IMPLEMENT LATER — strong enterprise differentiator | 1 week |
| **F9** | VS Code extension | IMPLEMENT LATER — best post-defense demo artifact | 1-2 weeks |
| **F10** | HyperRAPTOR (Poincaré ball, USE_HYPER_RAPTOR flag) | IMPLEMENT LATER — enable when GPU available | flag exists |
| **F11** | Azure Container Apps auto-scaling | IMPLEMENT LATER — ~50-line ACA YAML | 2 days |
| **F12** | Streaming progress SSE (partition-level events) | IMPLEMENT LATER — SSE endpoint exists | 2 days |
| **F13** | Real-time collaboration (WebSocket) | SKIP — high effort, wrong problem | — |

---

## Part 3 — Conference Strategy

### Which paper to write first

You cannot write 8 papers. Pick one. The decision depends on what results come out strongest after you run the experiments.

**If P2 results are strong** (reasoning model covers 4+ of the 7 Z3-unverifiable blocks):
→ Submit to **ASE 2026** or **ISSTA 2026**
→ Title: *"Three-Tier Verification for SAS-to-Python Migration: Formal Proof, Neural Reasoning, and Execution Equivalence"*
→ Core result: Venn diagram showing each tier catches a distinct error class. No single tier dominates.

**If P4 results are strong** (pipeline loses to long-context for programs under 200 blocks):
→ Submit to **ICSE 2026** or **FSE 2026**
→ Title: *"Chunking Considered Harmful? Empirical Analysis of Pipeline vs. Long-Context SAS Migration"*
→ Core result: crossover curve — pipeline wins above N blocks, long-context wins below. Architects now have a principled answer.

**If P3 results are strong** (DPO-aligned model reduces Z3 counterexample rate by >15%):
→ Submit to **NeurIPS 2026** or **EMNLP 2026**
→ Title: *"Formally-Verified Preference Optimization: Z3-Supervised DPO for Code Translation Alignment Without Human Labels"*
→ Core result: ECE and counterexample rate comparison: base model vs. DPO-Z3. First paper to use a formal prover as preference oracle.

**If P1 results are strong** (execution-grounded prompting improves accuracy on RETAIN/FIRST./LAST.):
→ Submit to **ASE 2026** or bundle with P2 as a combined system paper
→ Title: *"Execution-Grounded Translation: Resolving SAS Semantic Ambiguity via Behavior Examples"*

### Conference Tier Reference

| Conference | Rank | Focus | Fit for Codara |
|-----------|------|-------|----------------|
| ICSE | A* | Software engineering, broad | P4, system paper |
| FSE/ESEC | A* | Software engineering, broad | P4, P1 |
| ASE | A | Automated SE, AI tools | P1, P2, P5, P8 |
| ISSTA | A | Testing, verification | P2, P6, P7 |
| NeurIPS | A* | ML, broad | P3 only if ML results are exceptional |
| EMNLP | A | NLP, LLMs | P3 |
| MSR | A | Empirical, mining | P7, P4 |
| SANER | B | Legacy code, evolution | Full system paper |
| ICSME | B | Maintenance, migration | Full system paper, most accessible |

**Realistic first target for a PFE student:** ASE 2026 or ICSME 2026. Both are respected, both directly cover automated migration tools.

### The Minimum Viable Paper

If you want the highest probability of acceptance for your thesis defense timeline:

1. Build the SAS emulator (S0, 1 week)
2. Run P2 experiment: Z3 catches X errors on torture test, emulator catches Y, DeepSeek-R1 reasoning trace catches Z
3. Show the Venn diagram — each tier is necessary, no single tier dominates
4. Extend P1: show execution-grounded prompting improves accuracy specifically on the patterns none of the three tiers could previously verify

That is one coherent paper: *"Complementary Verification for SAS-to-Python Migration: When Formal Proofs, Execution Testing, and Neural Reasoning Each Win."*
Submit to ISSTA 2026 or ASE 2026. Both have a history of accepting empirical characterization papers with strong evaluation on a real system.
