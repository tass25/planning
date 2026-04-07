# Codara — Research & Extension Suggestions

---

## Already Implemented (in pipeline)

| Feature | Based On | Notes |
|---------|----------|-------|
| RAPTOR clustering | [RAPTOR paper, Sarthi et al. 2024] | Applied to code instead of text |
| Z3 formal verification | SMT solving (de Moura & Bjørner 2008) | 4 pattern families encoded |
| HyperRAPTOR (Poincaré ball) | Hyperbolic geometry for hierarchical data | SAS hierarchy maps naturally |
| QLoRA fine-tuning | [QLoRA paper, Dettmers et al. 2023] | Qwen2.5-Coder SFT + DPO |
| Reflexion retry | [Reflexion paper, Shinn et al. 2023] | Already in translation loop |
| Failure mode taxonomy | Original contribution | 9 modes, detection + rules |

---

## 🔬 Paper-Ready Contributions

### 1. Counterexample-Guided Neural Repair (Z3 Loop)
**Based on**: CEGAR (Clarke et al. 2000) + neurosymbolic AI
**Idea**: Z3 finds a concrete input where SAS and Python diverge → inject it into the LLM prompt → targeted repair → Z3 re-verifies. Loop until proof or timeout.
**Why it's novel**: First system to close the verification→repair→re-verification loop for LLM code migration. Other tools use Z3 as a post-hoc filter, not as a repair signal.
**Full paper**: `docs/reports/z3_neurosymbolic_paper.md`

---

### 2. Quantum Annealing for Code Partitioning
**Based on**: QUBO optimization, D-Wave quantum annealing
**Idea**: Finding optimal SAS program partition boundaries is NP-hard. Formulate as QUBO (each variable = merge this block with neighbor yes/no). Solve on D-Wave Leap (free research access) or quantum-inspired classical solver (SimCIM).
**Why it's novel**: First application of quantum annealing to code migration. Classical heuristics get stuck on large programs; quantum finds near-optimal globally.
**Effort**: High — needs QUBO formulation + D-Wave API access

---

### 3. Blockchain Proof Certificates for Regulated Industries
**Based on**: Ethereum/Hyperledger smart contracts + formal verification
**Idea**: When Z3 proves a translation correct → hash (SAS + Python + proof) stored on-chain. Smart contract auto-certifies the migration. Immutable, regulator-readable audit trail.
**Why it's novel**: FDA 21 CFR Part 11, SOX, Basel III all require auditable code change records. No migration tool provides cryptographically verifiable compliance certificates. This is a direct enterprise sale.
**Effort**: Medium — Ethereum or Hyperledger Fabric + Z3 hash export

---

### 4. Federated Knowledge Base Learning
**Based on**: Federated learning (McMahan et al. 2017), differential privacy
**Idea**: Banks/pharma companies can't share their SAS code. Federated learning lets each org train locally on their pairs, share only gradients (not data). Global KB improves for everyone with ε-DP guarantees.
**Why it's novel**: Directly solves the #1 enterprise adoption blocker. No migration tool addresses multi-org knowledge sharing with privacy guarantees.
**Effort**: High — needs FL infrastructure (Flower framework)

---

### 5. Execution-Based Semantic Equivalence Testing
**Based on**: Property-based testing (Hypothesis library), fuzzing
**Idea**: Generate synthetic DataFrames → run SAS logic (simulated) AND translated Python → compare outputs row-by-row. Divergences = translation bugs, automatically, without human review.
**Why it's novel**: Syntax checking is table stakes. Output-level equivalence testing is what production needs. The existing sandbox already executes Python — extend it to compare against a SAS emulator.
**Effort**: Medium — SAS emulator for core data step semantics is the hard part

---

### 6. Contrastive Embeddings for Cross-Language Code Similarity
**Based on**: Contrastive learning (SimCLR, Chen et al. 2020), CodeBERT
**Idea**: Fine-tune embeddings where semantically equivalent SAS and Python snippets are close in embedding space — regardless of syntax. Use gold standard pairs as positives, random pairs as negatives.
**Why it's novel**: Existing code embeddings (CodeBERT, Nomic) don't model cross-language semantic equivalence. Better retrieval = better RAG = better translations.
**Effort**: High — needs contrastive training loop on gold standard

---

### 7. Active Learning for KB Expansion
**Based on**: Active learning (uncertainty sampling), query-by-committee
**Idea**: Instead of randomly expanding the KB, identify which SAS patterns the model is most uncertain about (lowest confidence, most retries, most PARTIAL) → solicit human translations for exactly those.
**Why it's novel**: KB grows where it hurts most. Dramatically more efficient than random expansion.
**Effort**: Low — confidence scores already exist, just need sampling strategy + human interface

---

### 8. Supply Chain Trust Propagation (SBOM for Migration)
**Based on**: SBOM (Software Bill of Materials), CISA guidelines, supply chain security
**Idea**: Treat a SAS codebase as a software supply chain. Each macro/dataset is a component with a trust score. If `%utility_macro` is Z3-verified, all programs calling it inherit partial trust. Generate a Migration SBOM.
**Why it's novel**: EU Cyber Resilience Act mandates SBOMs. First migration tool to generate migration-level provenance manifests. Enterprise differentiator.
**Effort**: Medium — NetworkX dependency graph already exists, add trust propagation layer

---

### 9. Causal Inference for Translation Failure Diagnosis
**Based on**: DoWhy (Microsoft), CausalNex, Pearl's do-calculus
**Idea**: Build a causal graph of what features of SAS code *causally* produce failure modes — not just correlations. Enables minimal targeted interventions: fix the root cause, not the symptom.
**Why it's novel**: All current failure mode detection is correlational. Causal intervention means the repair is guaranteed to address the actual cause.
**Effort**: High — needs causal graph construction from failure log data

---

### 10. DPO Preference Loop from Human Corrections
**Based on**: Direct Preference Optimization (Rafailov et al. 2023), RLHF
**Idea**: Human corrections are negative examples (bad translation), validated successes are positive. Build preference pairs and run DPO on top of the SFT fine-tuned model. Self-improving loop.
**Why it's novel**: The pipeline already collects corrections. DPO turns them into training signal automatically.
**Effort**: Medium — dataset builder exists, needs DPO training loop (extend QLoRA notebook)

---

## Priority Matrix

| Suggestion | Impact | Effort | Paper? | Do First? |
|------------|--------|--------|--------|-----------|
| Z3 repair loop | ★★★★★ | Medium | ✅ | ✅ Already built |
| Active learning KB | ★★★★ | Low | ✅ | ✅ Quick win |
| Execution equivalence | ★★★★★ | Medium | ✅ | Next |
| DPO preference loop | ★★★★ | Medium | ✅ | Next |
| Blockchain certificates | ★★★★★ | Medium | ✅ | Month 2 |
| Supply chain SBOM | ★★★★ | Medium | ✅ | Month 2 |
| Quantum QUBO | ★★★★★ | High | ✅ | Month 3+ |
| Federated KB | ★★★★★ | High | ✅ | Month 3+ |
| Contrastive embeddings | ★★★★ | High | ✅ | Month 3+ |
| Causal inference | ★★★★ | High | ✅ | Research only |
