
# Defense Q&A — Codara / CDAIS+MIS
**PFE Jury Preparation — TekUp University**
*Coverage: Introduction → Methodology → Implementation → Research Paper → Hard attacks*

---

## LEVEL 1 — Warm-Up (Every jury asks these)

---

**Q1. Présentez-vous et votre projet en une minute.**

Codara is a SAS-to-Python conversion accelerator built over 15 weeks. It combines a LangGraph pipeline with RAG, RAPTOR clustering, and Z3 formal verification to automatically translate legacy SAS code into executable Python, and validate those translations semantically. My research paper, accepted to SCAM 2026, introduces CDAIS and MIS — two formally grounded methods that sit on top of the translation pipeline to catch bugs that pass sandbox execution but produce silent wrong results.

---

**Q2. C'est quoi SAS ? Pourquoi est-ce qu'on migre vers Python ?**

SAS (Statistical Analysis System) is a proprietary analytics language from the 1970s, dominant in finance, healthcare, and government. Organizations are migrating because Python is free, open-source, has a richer ecosystem (pandas, PySpark, scikit-learn), and SAS licenses cost millions per year. The problem is the migration is complex — SAS has constructs like RETAIN, LAG, and PROC SORT with no direct Python equivalent, and LLMs frequently mistranslate them silently.

---

**Q3. Qu'est-ce qu'un LLM ? Pourquoi l'utiliser pour la migration de code ?**

A Large Language Model is a neural network trained on hundreds of billions of tokens of text and code. It learns statistical patterns that let it translate between programming languages without explicit rules. We use LLMs because rule-based transpilers fail on complex constructs like nested macros or correlated PROC SQL subqueries. LLMs generalize to arbitrary patterns but introduce a new risk: code that executes correctly but produces wrong results.

---

**Q4. Quel est le problème central que vous résolvez ?**

LLMs produce semantic bugs in code migration: the translated Python runs without error, returns a DataFrame, but the numbers are wrong. Existing validation — sandbox execution, syntax checks — does not catch this. A cumsum() without a group reset produces plausible output on single-group data. The bug only appears with multiple groups. CDAIS and MIS are designed specifically to detect this class of silent semantic error.

---

**Q5. Citez un exemple concret de bug que votre système détecte.**

RETAIN_RESET (C1): In SAS, `retain total 0; if first.region then total = 0; total + amount;` resets the accumulator at each group boundary. A common LLM mistranslation is `df['total'] = df['amount'].cumsum()` — no group reset. On a single-group dataset this gives the right answer. The moment you have two regions, the numbers diverge. CDAIS synthesizes a 6-row witness (3 rows per group, all values = 1) that deterministically exposes this: oracle says [1,2,3,1,2,3], the buggy code says [1,2,3,4,5,6].

---

**Q6. Quelle est la différence entre une erreur syntaxique et une erreur sémantique ?**

A syntax error is caught at parse time — the code won't run at all. A semantic error means the code runs perfectly but produces wrong output. All six error classes in my taxonomy are semantic: the Python code is syntactically valid, passes import checks, executes without exceptions, and returns a plausible-looking DataFrame — the values are just wrong.

---

**Q7. Combien de semaines a duré le projet et qu'avez-vous livré ?**

15 weeks. Deliverables: a full-stack SAS→Python accelerator (FastAPI backend + React frontend + 8-node LangGraph pipeline), a knowledge base of 330 verified SAS→Python pairs in LanceDB, a benchmark suite with 61 gold-standard SAS files, 248 tests, Z3 formal verification, CDAIS adversarial synthesis, and MIS invariant validation. The research paper targets the SCAM 2026 conference.

---

## LEVEL 2 — Methodology

---

**Q8. Pourquoi avez-vous choisi une approche multi-couches de validation ?**

Because no single technique covers all failure modes. Sandbox execution checks that code runs. Z3 formally proves correctness for simple arithmetic patterns. SemanticValidator checks output equivalence on synthetic data. CDAIS adds class-specific adversarial witnesses with a formal certificate. MIS catches unknown bugs via invariant violation. Each layer has a different detection profile — they are genuinely complementary, not redundant.

---

**Q9. Expliquez CDAIS en une phrase, puis en détail.**

One sentence: CDAIS uses the Z3 SMT solver to synthesize the minimum-size dataset that deterministically exposes a specific class of semantic bug in a translated code.

In detail: For each of the 6 formalized error classes, we write a Z3 constraint system that encodes the exact divergence condition between the correct SAS computation and the buggy Python computation. We use `z3.Optimize` with a `minimize(sum(vars))` objective to find the smallest satisfying assignment. Z3 returns concrete integer values that we materialize into a pandas DataFrame — the witness. We then run both the SAS oracle and the Python translation on this witness. If outputs differ, the bug is exposed. If they match, we issue a coverage certificate: the translation is free from that error class for datasets of the same structural shape.

---

**Q10. Expliquez MIS.**

MIS (Migration Invariant Selection) answers: "which properties hold universally across all correct SAS→Python translations?" We start with 18 analyst-written candidate invariants — things like "output must be non-empty if input is non-empty" or "cumsum must be monotone for RETAIN without subtraction." For each candidate, we run it against 142 oracle-validated (SAS, Python) pairs. If the invariant holds on every oracle output for every applicable pair, it is confirmed. If it fails even once, it is rejected. 10 of 18 were confirmed. These confirmed invariants become a reusable specification: any future translation that violates them has a semantic bug.

---

**Q11. Quelle est la différence entre CDAIS et du fuzzing classique ?**

Fuzzing generates random or heuristic inputs and hopes they trigger a bug. It has no guarantee — for SORT_STABLE (C3), a single random trial has only a 25.5% chance of exposing the bug. CDAIS is deterministic: it encodes the divergence condition as a mathematical constraint and asks Z3 to solve it. Z3 either returns a witness (100% guaranteed to expose the bug in one trial) or proves the constraint is UNSAT (the bug cannot exist). No randomness, no multiple trials needed.

---

**Q12. Pourquoi Z3 ? Pourquoi pas un autre solveur ?**

Z3 is the industry-standard SMT solver, developed at Microsoft Research, with active maintenance, Python bindings (`z3-py`), and built-in optimization via `z3.Optimize`. The error classes I formalize are in the quantifier-free linear integer arithmetic (QF-LIA) fragment, which Z3 handles in polynomial time via the Simplex+DPLL(T) backend. This gives sub-100ms synthesis times. Z3 also has first-class support for minimization objectives, which is essential for producing small, readable witnesses.

---

**Q13. Expliquez le théorème de soundness des coverage certificates.**

Theorem: if a translation passes the CDAIS witness for class C (oracle output equals translation output on witness W), then the translation is free from class C for all datasets of the same structural shape.

Proof by contrapositive: assume the translation has the bug (B_C(p) = 1). The witness W is constructed so that any program exhibiting B_C must diverge from the oracle on W — this is guaranteed by the constraint encoding. Therefore if the translation has the bug, it must fail on W. Contrapositive: if it passes W, it does not have the bug.

The scope is explicitly limited to the same structural shape (same number of groups, same rows-per-group). We do not claim full behavioral equivalence.

---

**Q14. Pourquoi LOO-CV sur MIS ?**

Leave-one-out cross-validation tests whether confirmed invariants are stable or fragile — i.e., whether removing any single pair from the corpus would flip the decision. We ran LOO-CV on all 142 pairs: for each fold, we removed one pair and re-evaluated all 18 candidates on 141 pairs. Result: zero invariants flipped. This means the confirmed set reflects genuine SAS semantic properties, not corpus-specific sampling artifacts. Total LOO-CV time: 12.1 seconds on CPU.

---

**Q15. Pourquoi 18 invariants précisément ? Comment les avez-vous choisis ?**

The 18 candidates were derived from a manual analysis of SAS semantics across four categories: structural (row/column counts), relational (aggregation properties), ordering (sort stability), and semantic (LAG, RETAIN, boundary behavior). The number 18 was not chosen arbitrarily — it represents the exhaustive set of candidate properties I could derive from the SAS 9.4 Language Reference and expert domain knowledge. MIS then filters them empirically. That 8 were rejected is a feature, not a problem — it means MIS correctly identifies over-aggressive candidates that don't hold in real SAS.

---

**Q16. Pourquoi SORT_STABLE nécessite 17 lignes et pas 2 ?**

The 2-row minimal witness would work in theory — two rows with equal primary keys but different secondary values. In practice, numpy's `sort_values()` defaults to introsort, which uses insertion sort (stable) for arrays of ≤16 elements and switches to quicksort (unstable) at n=17. So for n≤16, numpy's "unstable" sort actually behaves stably, and the bug is invisible. We verified empirically: on numpy 1.26 + pandas 2.3, 17 equal-key rows deterministically reorder at position 16 in 100/100 trials. The minimality override encodes exactly 17 rows with strictly ordered secondary values — trivially solvable by Z3 (296ms).

---

## LEVEL 3 — Implementation & Architecture

---

**Q17. Expliquez l'architecture du système Codara.**

Three-tier stack: React/Vite frontend proxies to a FastAPI backend on port 8000. The backend triggers a LangGraph pipeline in a background task. The pipeline has 8 nodes: file_process → streaming → chunking → raptor → risk_routing → persist_index → translation → merge. State is a TypedDict checkpointed to Redis every 50 blocks. The vector knowledge base lives in LanceDB (768-dim Nomic embeddings). LLM audit logs go to DuckDB. The SQLite database handles API state (users, conversions, stages).

---

**Q18. Qu'est-ce que RAPTOR et pourquoi l'utiliser ?**

RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval) builds a hierarchical tree of SAS code blocks by clustering similar blocks with GMM and summarizing each cluster. This gives multi-granularity retrieval: when translating a complex block, we retrieve not just similar leaf-level examples but also cluster-level abstractions that capture patterns across multiple files. The advantage vs. flat KNN: higher hit-rate and MRR on complex (MOD/HIGH risk) partitions, where cross-file patterns matter.

---

**Q19. Comment fonctionne le RAG à 3 niveaux ?**

Static RAG for LOW-risk blocks: simple KNN search in LanceDB, top-5 examples. Graph RAG for blocks with cross-file dependencies: graph traversal via NetworkX to find structurally connected examples. Agentic RAG for MOD/HIGH/UNCERTAIN blocks: multi-step retrieval with escalated k, reflexion loops, and cross-verification. The router (`RAGRouter`) decides which paradigm based on the block's risk level and dependency count.

---

**Q20. Comment fonctionnent le circuit breaker et le rate limiter ?**

The `RateLimitSemaphore` limits concurrent LLM calls: 10 for Azure, 3 for Groq, to avoid rate-limit 429 errors. The `CircuitBreaker` tracks consecutive failures per provider: after 5 failures, the Azure breaker opens for 60 seconds; after 3 failures, the Groq breaker opens for 120 seconds. During open state, calls go directly to the next fallback. This prevents cascading failures when one provider is down.

---

**Q21. Pourquoi DuckDB pour les audit logs et pas SQLite ?**

DuckDB is a columnar OLAP database optimized for analytical queries — aggregations, time-series, GROUP BY. Audit logs are written sequentially (OLTP-like) but queried analytically (average latency by model, error rates over time, token consumption). SQLite is row-oriented and slower on such queries. DuckDB gives sub-second analytical queries on millions of rows. Also, DuckDB is embedded like SQLite — no separate server process needed.

---

**Q22. Pourquoi LanceDB pour la knowledge base et pas Pinecone ou Chroma ?**

LanceDB is embedded (no server), uses the Lance columnar format for fast vector scans, supports IVF indexing for large-scale ANN search, and runs entirely on-disk without a network round-trip. For a self-contained PFE project without cloud budget, it's the right choice. Pinecone would require API keys and internet access; Chroma adds a server dependency. LanceDB gives 768-dim cosine search on 330+ pairs in under 50ms.

---

**Q23. Expliquez le pipeline de streaming FSM.**

The streaming parser uses a producer/consumer pattern with an asyncio.Queue. `StreamAgent` (producer) reads SAS files line-by-line and pushes tokens. `StateAgent` (consumer) runs a Finite State Machine that tracks parser state: DATA_STEP, PROC_STEP, MACRO_DEF, etc. State transitions happen on keyword patterns. This handles files of any size in constant memory — we never load the entire file. Backpressure is implemented via `asyncio.Queue(maxsize=1000)`: the producer blocks when the queue is full.

---

**Q24. Comment fonctionne le ValidationAgent sandbox ?**

The ValidationAgent wraps Python `exec()` in a `multiprocessing.Process` (not threading, which leaks). It removes dangerous builtins from the execution namespace: `open`, `__import__`, `exec`, `eval`, `compile`, `exit`, `quit`, `input`, `breakpoint`. On timeout, it calls `process.kill()` (not `.join(timeout)`, which would let the subprocess continue). The isolation is true OS-level process isolation, compatible with Windows (no `signal.alarm` dependency).

---

**Q25. Pourquoi LangGraph plutôt qu'un pipeline séquentiel classique ?**

LangGraph provides a StateGraph where each node receives the full pipeline state and returns a partial update. This enables: (1) conditional edges (skip RAPTOR on single-block files), (2) Redis checkpointing at arbitrary points for resumability after crashes, (3) clean error isolation — a node failure appends to `state["errors"]` without crashing the whole pipeline. A sequential script would require manual state passing, no built-in checkpointing, and harder error isolation.

---

## LEVEL 4 — Research Paper Deep Dive

---

**Q26. Quelle est votre Research Question exacte ?**

"Can we generate formally minimal test inputs that deterministically expose specific semantic error classes in LLM-based legacy code migration, and automatically confirm invariants that characterize correct migration behavior from a verified corpus, without requiring a SAS runtime or manual specification?"

The key constraints: deterministic (not probabilistic), formally minimal (smallest possible witness), no SAS runtime (Python oracle re-implements SAS semantics), no manual specification (invariants are confirmed empirically from data, not proven by hand).

---

**Q27. Quelles sont vos 3 contributions scientifiques ?**

1. CDAIS and a six-class error taxonomy: the first use of SMT synthesis for formally minimal adversarial test generation in LLM-based code migration. Each witness comes with a coverage certificate.

2. MIS: the first corpus-driven migration invariant validation framework for paired legacy→modern code. It confirms which of 18 analyst-provided candidates hold universally, producing an empirically grounded specification.

3. Experimental evaluation with measured results: CDAIS provides deterministic 1-trial detection for 6/6 classes; MIS confirms 10/18 invariants on a 142-pair corpus; LOO-CV confirms zero fragile invariants.

---

**Q28. Expliquez vos 3 datasets et pourquoi vous en avez besoin de 3 différents.**

**TC (330 pairs):** The Codara LanceDB knowledge base, used only for error frequency analysis in the taxonomy. The KB verifier does not execute code, so TC cannot validate behavioral correctness.

**GSC (61 SAS files):** Gold standard corpus with `.gold.json` annotations. Used for CDAIS witness validation and Z3 evaluation. No Python translations are present in the annotations, so GSC cannot be used for MIS.

**VTP (142 pairs):** Verified Translation Pairs, the only dataset with both SAS and correct Python. Used exclusively for MIS invariant confirmation. 12 cross-provider verified pairs + 130 enterprise pairs reviewed by a senior SAS developer.

Each dataset serves exactly one role — cross-using them would conflate distinct evaluation questions.

---

**Q29. Pourquoi 10/18 invariants confirmés et pas plus ? Les 8 rejetés sont une faiblesse ?**

No — the 8 rejected invariants are a feature. Three of them (COLUMN_SUPERSET at 96.6%, ROW_PRESERVATION at 92.9%, ROW_EQUALITY_SORT at 58.3%) were confirmed on the original 12-pair corpus but rejected when we scaled to 142 pairs. This proves MIS works correctly: it identifies invariants that don't hold universally in real SAS — confirming them would have produced false positives. SORT_KEY_SORTED was rejected because SAS PROC SORT does not always guarantee the output is globally sorted on all BY variables in all contexts. LAG_NULL_FIRST_ROW failed at 0% — our LAG oracle had a boundary semantics discrepancy with SAS 9.4, which the rejection surfaced and confirmed.

---

**Q30. Comment avez-vous construit l'oracle SAS ? Vous n'avez pas SAS installé ?**

The oracle is a Python re-implementation of each supported SAS construct. For RETAIN, we implement the accumulator with group-boundary reset using pandas groupby. For LAG, we implement the implicit queue semantics. For PROC SORT, we use `sort_values(kind='mergesort')`. For NULL_ARITHMETIC (SUM function), we use `pd.Series.fillna(0)` before summing. Each oracle function was validated against the SAS 9.4 Language Reference and cross-checked against manually curated gold-standard outputs. The rejected LAG_NULL_FIRST_ROW invariant actually helped surface a discrepancy in the LAG oracle, which we then corrected.

---

**Q31. Pourquoi votre SCS (Semantic Correctness Score) est 0.552 ? C'est pas suffisant ?**

0.552 means 5/10 blocks on the torture test are VERIFIED or LIKELY_CORRECT, 2 are UNCERTAIN, 3 are LIKELY_INCORRECT. This is intentional — the torture test was designed to contain the hardest SAS patterns: RETAIN with FIRST./LAST., correlated SQL subqueries, hash objects, nested macros, PROC TRANSPOSE. These are patterns that LLMs consistently struggle with. A 55% semantic correctness rate confirms the core motivation: 100% syntactic success versus 55% semantic correctness is exactly the gap CDAIS and MIS are designed to address. On simpler production SAS code, the rate is higher.

---

**Q32. Votre papier dit que CDAIS ne garantit pas d'équivalence complète. C'est suffisant pour la pratique ?**

Yes, for two reasons. First, full behavioral equivalence is undecidable in general (reduction to the halting problem). No tool can provide it. Second, in practice, the six formalized error classes cover the large majority of observed semantic bugs in SAS→Python migration. A coverage certificate for all six classes on the same structural shape gives practitioners strong confidence — stronger than any heuristic testing approach — at a cost of 73ms per translation. The certificate explicitly states its scope. Transparency about limitations is a scientific contribution, not a weakness.

---

**Q33. Comment comparez-vous à Daikon ?**

Daikon discovers invariants from scratch by running a single program and observing execution traces against a template grammar. MIS differs on three axes: (1) MIS operates on paired executions — both the SAS oracle and the Python translation — not a single program; (2) MIS has a fixed 18-candidate library, so it performs selection, not discovery; (3) MIS operates on tabular DataFrame semantics, not general program variables. Daikon would not be directly applicable here because it doesn't reason about pairs and doesn't handle DataFrame-level properties like column dtype stability or row count invariants across two programs.

---

**Q34. Pourquoi cibler SCAM 2026 spécifiquement ?**

SCAM (Source Code Analysis and Manipulation) is a premier IEEE venue for research on automated code analysis, transformation, and testing. It directly covers LLM code translation, formal verification, and test generation — exactly our contributions. The audience includes researchers from ICSE, ASE, and ISSTA who will evaluate the technical rigor of our SMT encoding and the scientific validity of our experimental methodology.

---

## LEVEL 5 — Hard / Attack Questions

---

**Q35. Votre corpus VTP contient 130 paires annotées par une seule personne. C'est un biais ?**

Yes, and we acknowledge it explicitly in the Limitations section. Single-annotator validation can introduce confirmation bias. The mitigation is LOO-CV stability (zero fragile invariants across all 142 folds) and the fact that the senior SAS developer works with production SAS codebases daily, giving domain authority. Future work should include double annotation on 30-50 pairs with Cohen's κ to quantify inter-rater agreement. We name this explicitly rather than hiding it.

---

**Q36. Si Z3 peut prouver seulement 30% des traductions, ça ne limite pas beaucoup votre système ?**

30% formal proof is not a failure — it's expected. Z3 operates in the quantifier-free linear arithmetic fragment. SAS constructs like RETAIN, LAG, hash objects, and PROC TRANSPOSE are not encodable in this fragment. The 30% corresponds exactly to the blocks with simple patterns (groupby aggregation, sort dedup, boolean filters). For the remaining 70%, CDAIS and MIS provide complementary validation that Z3 cannot. The five-layer pipeline was designed precisely because no single method covers everything.

---

**Q37. Votre système nécessite un "SAS oracle" — mais comment validez-vous que l'oracle lui-même est correct ?**

Three validation methods: (1) the oracle functions were written against the SAS 9.4 Language Reference, the authoritative specification; (2) they were unit-tested with 36 CDAIS-specific tests and 34 Z3 verification tests, all passing; (3) the rejected LAG_NULL_FIRST_ROW invariant (0% oracle pass rate) revealed a boundary semantics error in our LAG oracle, which we then corrected. This self-correction demonstrates that MIS itself can surface oracle errors — the rejected invariants are diagnostic tools.

---

**Q38. Pourquoi pas utiliser un vrai moteur SAS pour l'oracle ?**

Two reasons. First, SAS is proprietary software with expensive commercial licensing — inaccessible in a PFE context. Second, a Python oracle is reproducible, open, and testable by any reviewer without a SAS installation. The SCAM paper explicitly frames reproducibility as a contribution: all results (CDAIS, MIS, Z3) are fully reproducible from the artifact without any external LLM API or proprietary software. The scope limitation is clearly stated.

---

**Q39. CDAIS génère des données synthétiques minimales — mais les bugs réels apparaissent avec des vraies données de production. Votre approche est-elle écologique ?**

The coverage certificate is scoped to structural shape, not specific values. If the witness uses G=2 groups, R=3 rows, the certificate holds for all datasets with 2 groups of 3 rows with the same value ranges — not just the specific 1,1,1,1,1,1 witness. For production data validation, the practitioner would use domain-appropriate DummyDataGenerator instances, not the minimal witnesses. The witnesses serve two purposes: (1) development-time adversarial testing with interpretable inputs, (2) coverage certificates that are mathematically scoped. Production testing uses a different data generation path.

---

**Q40. Votre taxonomie a 6 classes — comment savez-vous que vous n'en manquez pas une 7ème critique ?**

We don't claim completeness. The six classes were derived from qualitative analysis of the 330-pair Codara corpus and represent the patterns observed most frequently. The paper explicitly states: "Together, these six classes cover the large majority of observed semantic errors in SAS→Python migration." Future work item (1) is "extending the taxonomy from 6 to 20+ classes by automated mining of corpus failures." MIS is designed to catch violations of confirmed invariants even for unformalized error classes — it provides complementary coverage precisely for bugs outside the taxonomy.

---

**Q41. Pourquoi "Constraint-Driven Adversarial Input Synthesis" et pas simplement "Test Data Generation" ?**

Three specific properties justify the name. "Constraint-Driven": the inputs are derived from Z3 constraint systems, not random or heuristic. "Adversarial": the inputs are specifically designed to expose bugs — they are the worst-case inputs for a given error class. "Synthesis": Z3 synthesizes the inputs from a formal specification rather than sampling from a distribution. "Test Data Generation" would imply any method that produces test data, including random or heuristic approaches. CDAIS is a specific, formally grounded algorithm — the name should reflect that.

---

**Q42. Vous dites que les invariants confirmés sont "empiriquement universels" — c'est suffisant pour une spécification formelle ?**

It is sufficient for practical engineering validation, but not for formal correctness proofs. The distinction is explicit: confirmed invariants are empirically universal on the 142-pair VTP corpus. They are not formally proven for all inputs. This makes them closer to property-based testing specifications than formal theorems. The value is pragmatic: a translation that violates a confirmed invariant breaks a property that holds for every verified correct translation in the corpus — that is a strong signal. We do not claim formal completeness, and the paper clearly differentiates "empirically grounded specification" from "formal proof."

---

**Q43. Si quelqu'un réplique votre expérience avec un corpus différent, obtiendrait-il les mêmes 10 invariants ?**

Not necessarily. The composition of confirmed invariants depends on the corpus. We showed this explicitly: scaling from 12 to 142 pairs changed the confirmed set (3 demoted, 3 promoted). A corpus with more PROC TRANSPOSE examples might reject MEANS_AGGREGATION_MONOTONE. A corpus with more complex MERGE chains might reject MERGE_OUTER_ROWCOUNT. LOO-CV stability at 142 pairs gives confidence that the current set is stable at this corpus size. Full generalization requires a larger, more diverse corpus — which we identify as a threat to external validity and a direction for future work.

---

**Q44. Vous avez 248 tests — quel est votre coverage ? Y'a des parties non testées ?**

We did not enforce a specific coverage threshold in CI (target ≥80%). Known untested areas: the RAPTOR HyperRAPTOR (Poincaré ball) hyperbolic clustering path is experimental and not fully unit-tested. The LocalModel (llama-cpp Tier 0) path lacks integration tests because it requires a GGUF model file not committed to the repo. The GitHub OAuth callback is a stub. These are acknowledged gaps — the core translation pipeline, all 6 CDAIS classes, all 18 MIS invariants, and the Z3 verification paths are covered.

---

**Q45. Quel est l'overhead de CDAIS sur le pipeline de traduction ? Est-ce viable en production ?**

CDAIS synthesis: ~73ms average per witness, parallelized across applicable classes with asyncio. For a block with all 6 classes applicable (rare), worst case ~300ms (SORT_STABLE dominates at 296ms). Compare: a single LLM call takes 5-30 seconds. The total CDAIS overhead per translation is well under 1 second — negligible relative to LLM latency. MIS runs in 937ms for the full 142-pair corpus validation; for a single translation check, it runs applicable invariants only, typically <50ms. Both are viable in production as post-validation layers.

---

**Q46. Pourquoi votre fallback chain est Ollama → Azure → Groq ? Pourquoi pas une approche ensembliste ?**

Ensemble approaches would require running multiple LLMs in parallel and majority-voting on outputs — 3x the cost and 3x the latency per translation. The fallback chain minimizes cost (use the cheapest/fastest first) while ensuring availability. Groq serves as both a fallback and an independent cross-verifier: the cross-verification (Prompt C) uses Groq in a separate context from the primary translation, giving genuine independence without the full cost of an ensemble. This is a pragmatic engineering tradeoff — the paper focuses on the validation layer, not LLM selection.

---

**Q47. Qu'est-ce que vous auriez fait différemment avec 6 mois de plus ?**

Four things: (1) automate invariant candidate generation from corpus failure analysis instead of handwriting the 18 candidates; (2) apply CDAIS and MIS to SAS→PySpark and COBOL→Java to demonstrate generality; (3) use confirmed invariants as soft constraints during LLM generation (not just post-hoc checking) — potentially reducing the repair rate; (4) add inter-rater agreement (Cohen's κ) on the VTP corpus annotation. The LOO-CV stability at 142 pairs already provides strong evidence, but double annotation would strengthen external validity for a journal submission.

---

**Q48. Quelle est la vraie nouveauté scientifique par rapport à l'état de l'art ?**

Three things that did not exist before this paper:

1. **SMT synthesis for adversarial test generation in LLM code migration**: TransCoder, Avatar, and Pan et al. study the bug classes but provide no formal detection method. UniTrans uses heuristic test generation without formal witnesses or coverage certificates.

2. **Coverage certificates scoped to structural shape**: no prior work provides a formal guarantee (not just probabilistic coverage) that a translation is free from a specific error class.

3. **Corpus-driven invariant selection for paired legacy→modern code**: Daikon discovers invariants from single programs; MIS works on paired executions with DataFrame semantics and corpus-based confirmation. No prior work formalizes migration invariants for SAS→Python specifically.

---

**Q49. Votre papier utilise le mot "formally grounded" dans le titre. Est-ce justifié ?**

Yes. "Formally grounded" is deliberately precise — not "formally proven" and not "heuristic." CDAIS is grounded in formal SMT constraints: the witness satisfies a mathematically stated divergence condition, and the coverage certificate follows from a proven theorem (Theorem 1 in the paper). MIS is grounded in empirical corpus validation with LOO-CV stability. Neither is a full formal proof of translation correctness (which is undecidable) — but both have formal structure that random or heuristic testing lacks. The title accurately scopes the claim.

---

**Q50. Dernière question : quel impact réel ce travail peut-il avoir dans l'industrie ?**

Organizations like Deloitte, SAS Institute clients, and healthcare systems spend millions migrating SAS to Python and discovering silent wrong results in production months later. CDAIS provides a development-time validation layer that catches the most common bug classes before deployment, with human-readable 6-17 row explanations. MIS provides a reusable specification — once confirmed, the 10 invariants can be applied to any future translation in the applicable SAS categories without re-running the corpus. Together they shift semantic validation from "hope the numbers look right" to a structured, reproducible, formally grounded process. That is commercially significant.

---

*Total: 50 questions — from presentation warmup to formal proof attacks.*
*Tip: for Q9, Q13, Q26, Q27 — learn these by heart. The jury will probe these hardest.*

---

## PART 2 — Additional Questions (Report Chapters, Industrial Context, Evaluation Results)

---

## LEVEL 1 — Context & Host Company (Deloitte)

---

**Q51. Pourquoi Deloitte avait besoin de ce projet ? Quel était le besoin industriel réel ?**

Deloitte Tunisia's Data department (created in 2026) serves clients whose ETL pipelines, regulatory reporting, and statistical models are written in SAS — codebases with hundreds of thousands of lines accumulated over decades. SAS licenses cost millions per year. The client pressure to migrate to open-source Python is economic, not technical. But manual rewriting at that scale is impossible: the Data team needed an accelerator that a data engineer could point at a multi-file SAS project and receive a working Python script with a confidence signal. That is exactly what Codara delivers.

---

**Q52. Quelle était votre mission exacte chez Deloitte ?**

Four deliverables were negotiated at kickoff: (1) a working backend API implementing the 8-stage pipeline; (2) a React frontend with upload, monitoring, diff view, and admin panels; (3) a gold-standard evaluation corpus of 50 annotated SAS files (721 blocks); (4) a formal evaluation report. All four were completed within the four-month sprint. The internship ran from February 9 to June 9, 2026.

---

**Q53. Qu'est-ce que le département Data de Deloitte Tunisia fait concrètement ?**

It provides data engineering and analytics capabilities to enterprise clients across finance, banking, telecoms, energy, and public administration in Tunisia. Specifically, it helps clients whose pipelines use SAS for ETL, statistical modelling, and regulatory reporting — which are exactly the use cases Codara targets. The department was newly established in 2026, so Codara was one of its first internal R&D projects.

---

**Q54. Pourquoi vous avez choisi Python comme langage cible et pas PySpark ou R ?**

Python with pandas/NumPy is the dominant open-source analytics stack. It has the largest ecosystem, the most community support, and the most overlap with Deloitte's client environments. SAS→R was considered but R has a smaller enterprise footprint in Tunisia. PySpark is in scope at the pipeline architecture level (the `target_runtime` field exists) but is scoped out of the current frontend — it's a deliberate future extension. The 80/20 rule applies: most production SAS falls within BASE SAS patterns that map cleanly to pandas.

---

## LEVEL 2 — Methodology (DSR + Agile)

---

**Q55. C'est quoi DSR ? Pourquoi l'avez-vous choisi plutôt que Scrum ou CRISP-DM ?**

DSR (Design Science Research), codified by Hevner et al. (2004), is a research paradigm from Information Systems that frames the output as a designed artefact and requires its evaluation against explicit utility claims. It mandates: problem awareness, suggestion of a novel solution, development, evaluation, and conclusion. We chose DSR because Codara is both a research artefact (with testable novelty claims) and a software deliverable. Pure Scrum provides no scaffolding for scientific evaluation. Pure CRISP-DM is designed for data-mining with existing datasets, not novel software construction. DSR gave us the scientific frame; Agile gave us the sprint discipline to deliver working code at every checkpoint.

---

**Q56. C'est quoi un "design cycle" dans DSR ? Comment ça se mappe sur vos sprints ?**

DSR defines five design cycles: Problem Awareness → Suggestion → Development → Evaluation → Conclusion. These mapped naturally onto the 15-week sprint structure. Weeks 1-2: Problem Awareness (file analysis, corpus construction). Weeks 3-8: Suggestion + Development (streaming, boundary detection, RAPTOR, orchestration). Weeks 9-12: Development + Evaluation (translation, ablation). Weeks 13-15: Consolidation + Conclusion (Z3, CDAIS, MIS, report). Each sprint produced a benchmark result that fed back into the next sprint's design — DSR's evaluation cycle was continuous, not a one-off end-of-project exercise.

---

**Q57. Qu'est-ce que MoSCoW et comment l'avez-vous utilisé ?**

MoSCoW (Must/Should/Could/Won't) is a requirements prioritization technique. We applied it to the 30 functional requirements. "Must" requirements form the minimum viable system: FSM parser, boundary detection, complexity scoring, translation with structured output, sandboxed validation, REST API, JWT authentication, polling. "Should" requirements are quality improvements: Z3 SMT verification, CDAIS synthesis, SemantiCheck scoring, CEGAR repair. "Could" requirements are nice-to-have: KB management UI, admin dashboard, GitHub OAuth. "Won't" (in current scope): SAS/IML, SAS/GRAPH, interactive sessions. This framing helped us hit all Must requirements while delivering most Should requirements within four months.

---

**Q58. Comment avez-vous géré la dualité recherche-industrie dans votre projet ?**

The tension was real and managed explicitly. The industrial side (Deloitte) needed a deployable system — so every sprint produced a working artefact with tests, not just a research prototype. The academic side needed measurable novelty claims — so every sprint also produced a benchmark result: boundary F1 on the gold corpus, RAPTOR retrieval advantage in the ablation study, Z3 verification rate on the torture test. The DSR framing forced both: DSR mandates that the artefact solve a relevant problem better than alternatives AND that the demonstration meet research rigour standards. Neither could be sacrificed for the other.

---

## LEVEL 3 — Evaluation Results & Numbers

---

**Q59. Quels sont vos résultats quantitatifs les plus importants ?**

Six key numbers from the evaluation chapter:
- **72.4%** translation success rate (target: 70%) — met
- **96.8%** syntax-valid merged output (target: 95%) — met  
- **+12 pp** RAPTOR advantage on MOD/HIGH partitions (target: ≥10%) — met
- **ECE = 0.061** complexity calibration (target: <0.08) — met
- **79.3% F1** boundary detection (target: 90%) — **missed**
- **53.7%** hard-tier translation success — **missed**
- Streaming: 10K-line file in 1.34 seconds, 61 MB memory (target: <2s, <100 MB) — met

---

**Q60. Vous avez raté la boundary detection à 79.3% au lieu de 90%. Pourquoi ?**

Two root causes. First, the deterministic detector (lark/regex) achieved only 76.8% F1 because the lark grammar is a partial SAS grammar — it covers the most common DATA/PROC patterns but fails on macro-parameterised code sections (F1 = 52.1% on those). Second, the LLM fallback (activated for 21.1% of blocks) only contributed 64.5% accuracy on its assigned cases, with 15.1% outright failures on deeply nested `%DO/%END` macro blocks. The root architectural cause: we didn't build a full SAS macro pre-processor. Without pre-expansion, the boundary detector sees the macro call, not its expanded content. This is acknowledged in the conclusion as an architectural shortcut we'd correct in a second version.

---

**Q61. 53.7% sur les blocs high-complexity, c'est acceptable ?**

Honestly, no — and the report says so explicitly. 53.7% means nearly half of hard-tier blocks receive a PARTIAL or FAILED status. But context matters: "hard tier" includes deeply nested macro frameworks, hash-object joins, correlated PROC SQL subqueries, and multi-step RETAIN patterns — exactly the constructs that no existing commercial tool handles at all. Those tools produce 0% on this category because they refuse to process the files. 53.7% with structured repair hints and a SemantiCheck score telling the engineer which blocks need manual attention is still materially better than the alternative. The 90% target for hard-tier was aspirational; the conclusion identifies macro pre-expansion and KB expansion (to 500+ pairs) as the concrete path to improvement.

---

**Q62. Pourquoi vous avez ciblé 90% de boundary detection mais n'atteint que 79.3% ? C'était réaliste ?**

In retrospect, 90% required a full SAS grammar with macro expansion, which was out of scope for a 4-month sprint. The 90% target was set based on the deterministic component's performance on simple patterns (F1 = 91.3% for standard DATA/PROC alternation) and was too optimistic about the macro-heavy portion of the corpus. This is a lesson in requirements calibration: targets should be set after profiling the hardest cases, not after benchmarking the easy ones. The 79.3% achieved is a defensible result for a partial grammar + LLM fallback system, and the gap is precisely characterized with a concrete fix.

---

**Q63. Expliquez votre système de scoring SemantiCheck en 4 couches.**

SemantiCheck assigns a Semantic Correctness Score (SCS) by compositing four orthogonal verification signals:

- **L1 (Z3 formal proof):** UNSAT on the SMT query → formal guarantee. Highest weight. Applies to ~30% of blocks.
- **L2 (Behavioral/oracle):** Python SAS oracle run on adversarial synthetic inputs. Compares output DataFrames.
- **L3 (CDAIS adversarial):** Runs all applicable CDAIS witnesses. Pass = class-specific certificate.
- **L4 (LLM-as-oracle):** Sends the SAS code + a synthetic input to an LLM and asks it to predict the expected SAS output. Compares with Python translation output. Imperfect but adds signal where the other layers can't.

SCS categories: VERIFIED (L1 proof + all other layers pass), LIKELY_CORRECT (≥3 layers pass), UNCERTAIN (2 layers pass), LIKELY_INCORRECT (<2 layers pass). On the torture test: 5/10 blocks are VERIFIED or LIKELY_CORRECT, 2 UNCERTAIN, 3 LIKELY_INCORRECT.

---

**Q64. Qu'est-ce que le "torture test" et pourquoi 10 blocs seulement ?**

The torture test (`backend/tests/fixtures/torture_test.sas`) is a hand-crafted 10-block SAS file containing the 10 hardest migration patterns: RETAIN with carry-forward, FIRST./LAST. group detection, correlated PROC SQL, nested macro expansion, hash object lookup, PROC MEANS, PROC TRANSPOSE, LAG queue semantics, missing-value arithmetic (SUM function), and multi-file %INCLUDE reference. 10 blocks was deliberate — each block is a worst-case representative of one failure category. A 100-block test would dilute the signal with easy cases. The torture test measures worst-case performance, not average performance. Both LLMs tested (minimax-m2.7:cloud, nemotron-3-super:cloud) achieved 10/10 execution (syntactic success) with 3/10 formal proofs — confirming that execution ≠ semantic correctness.

---

**Q65. Votre ECE = 0.061 — expliquez ce que ça signifie concrètement.**

ECE (Expected Calibration Error) measures the gap between predicted confidence and empirical accuracy. ECE = 0.061 means that on average, when the complexity classifier predicts HIGH risk with 80% confidence, the block is empirically HIGH risk in ~74-86% of cases — a 6.1 percentage-point average deviation. A perfectly calibrated model has ECE = 0. ECE = 0.061 is well within our 0.08 threshold and means the routing logic (which sends partitions to different RAG tiers based on predicted risk level) is receiving reliable probability inputs. Platt scaling was applied post-training to achieve this — without it, logistic regression's raw outputs were overconfident by ~8-10 pp on HIGH-risk predictions.

---

**Q66. Qu'est-ce que RAPTOR vous apporte concrètement ? Vous dites +12pp — par rapport à quoi ?**

+12 percentage points in hit-rate@5 on MODERATE and HIGH complexity partitions compared to flat-index KNN retrieval (same LanceDB corpus, same query, same k=5). Flat KNN finds the 5 most similar leaf-level KB entries by cosine similarity. RAPTOR also returns cluster-level summaries, so a query about "BY-group running total with RETAIN reset" can match both a specific leaf example AND a cluster summary for "group accumulation patterns" — surfacing examples that are semantically related but not lexically similar to the query. This matters most for complex partitions that use combinations of constructs; single-construct queries already work well with flat KNN. The ablation study ran both systems on the same 200-partition evaluation set.

---

## LEVEL 4 — Architecture Deep Dive

---

**Q67. Pourquoi 8 étapes dans le pipeline et pas 5 ou 15 ?**

The 8 stages reflect a natural decomposition of the problem into four logical phases: parsing (file_process + streaming), partitioning (chunking + raptor), routing and translation (risk_routing + persist_index + translation), and output (merge). Each stage has a clearly distinct responsibility with no overlap. The history: the system started with 11 nodes in Week 13's consolidation, which was reduced to 7, then 8 (MergeAgent was separated from TranslationPipeline). 11 was too granular (separate nodes for persistence and indexing that should be sequential in the same step), 7 too coarse (merge and translation share nothing and warrant separate checkpointing). 8 is the right granularity for this problem.

---

**Q68. Pourquoi SQLite pour la base de données API plutôt que PostgreSQL ?**

Three reasons: (1) simplicity — a single file, zero configuration, no separate server process; (2) WAL (Write-Ahead Log) mode handles concurrent readers without locks, sufficient for single-server deployment; (3) SQLAlchemy 2.0 makes PostgreSQL migration a one-line connection string change when needed. The production deployment at Deloitte scale would need PostgreSQL for connection pooling and horizontal scaling — this is acknowledged in the conclusion. For a PFE project, SQLite in WAL mode hits all the non-functional requirements: p95 API response ≤200ms, no deadlocks observed in testing.

---

**Q69. Pourquoi Redis pour le checkpointing et pas une table SQLite supplémentaire ?**

Redis is an in-memory key-value store optimized for sub-millisecond writes. Checkpointing happens every 50 processed blocks — frequent writes that would create excessive I/O contention on SQLite if added to the same file as the API database. Redis also handles TTL (time-to-live) natively: checkpoint keys expire after 24 hours automatically, no cleanup job needed. The pipeline state (TypedDict with serialized partition lists) can reach several MB — Redis handles this efficiently. SQLite would work but adds I/O latency to the hot path of the pipeline.

---

**Q70. Comment fonctionne la résolution de dépendances cross-file ?**

The `CrossFileDepsResolver` runs during `file_process`. It scans each SAS file for `%INCLUDE` statements, libref references (`LIBNAME src "path"`), and macro call sites (`%macro_name(...)`). It builds a directed dependency graph in NetworkX: nodes are file IDs, edges are dependency links. Then it runs topological sort to determine the order in which files must be translated (a file that includes a macro library must be processed after that library is parsed). SCC (Strongly Connected Component) analysis detects circular dependencies — treated as warnings. The result: each partition's `dependencies` list contains UUIDs of partitions it depends on, which Graph RAG uses to retrieve upstream context.

---

**Q71. Comment fonctionne le CEGAR repair loop ?**

After Z3 returns a counterexample (a concrete input where the translated Python diverges from the SAS oracle), the CEGAR loop: (1) materializes the counterexample as a DataFrame; (2) runs both the SAS oracle and the Python translation on it to show the divergence numerically; (3) constructs a targeted repair prompt: "The translation fails on this input: [counterexample]. The oracle produces [X], your translation produces [Y]. Fix the translation." (4) sends the repair prompt to the LLM; (5) re-runs Z3 on the repaired translation. If Z3 returns UNSAT, the loop terminates with a verified repair. If not, the loop repeats up to a budget (3 iterations). CEGAR identified 43 real errors invisible to the test harness in the full evaluation run.

---

**Q72. Expliquez la feature engineering pour le complexity scorer.**

The ComplexityAgent extracts 18 lexical and syntactic features without any LLM call — all O(n) over the tokenized source:
- **Token counts**: total tokens, unique identifiers, distinct PROC names
- **Structural**: nesting depth (max nested DO blocks), number of BY clauses, number of macro references (`%macro_name`)
- **Dependency**: number of inter-file dependency edges, cross-libref references
- **Semantic flags**: presence of hash object declarations, presence of PROC SQL with subqueries, presence of RETAIN + BY, presence of LAG()

These 18 features feed a multinomial logistic regression (4 classes: LOW/MOD/HIGH/UNCERTAIN) trained on the 45-file gold standard corpus with Platt scaling. ECE = 0.061 was measured on the held-out 20% split.

---

**Q73. Pourquoi Nomic Embed v1.5 pour les embeddings et pas OpenAI text-embedding-3 ?**

Nomic Embed v1.5 produces 768-dimensional vectors, is open-source, runs locally via sentence-transformers, requires no API key, and is specifically optimized for code-mixed text (code + natural language descriptions). OpenAI's embedding model requires API calls (latency + cost per lookup) and would create a hard dependency on external infrastructure even for retrieval. For a system targeting offline/on-premises deployment at Deloitte, local embeddings are a hard requirement. The quality difference on SAS code retrieval is minimal — we verified this by comparing retrieval precision on 50 gold pairs.

---

## LEVEL 5 — Theoretical Foundations (Jury traps)

---

**Q74. Expliquez le PDV (Program Data Vector) de SAS et pourquoi il pose un problème de traduction.**

The Program Data Vector is SAS's execution model: for each observation (row) in an input dataset, SAS initializes a scratch buffer (the PDV), populates it with the current row's values, executes the DATA step body, and writes the PDV to the output dataset. At the start of each new observation, variables reset to missing — unless RETAIN is specified. This is fundamentally different from pandas, which operates on entire columns (set-oriented). A SAS DATA step with RETAIN accumulates row-by-row state; the equivalent in pandas requires `groupby().cumsum()` or `apply()` — the translation is non-trivial and depends on whether the accumulation resets at group boundaries. No rule can handle all RETAIN patterns deterministically.

---

**Q75. Qu'est-ce que la théorie de Rice et pourquoi elle justifie votre approche par couches ?**

Rice's theorem states that any non-trivial semantic property of programs (including behavioral equivalence) is undecidable — no algorithm can decide it for all programs in finite time. This means full equivalence checking of SAS→Python translations is theoretically impossible in general. This is why a layered approach is necessary: Z3 proves equivalence for the decidable fragment (linear arithmetic, boolean logic, sort semantics), CDAIS provides class-specific partial equivalence certificates, and MIS provides empirical validation for the rest. Each layer is sound within its scope, and together they cover the practical migration scenarios without claiming the undecidable full equivalence.

---

**Q76. Qu'est-ce que le Platt scaling et pourquoi l'avez-vous utilisé ?**

Platt scaling is a post-hoc probability calibration technique: after training the logistic regression classifier, you fit a second logistic regression on the classifier's raw output scores (not the class labels) using a held-out calibration set. This corrects systematic over- or under-confidence. We found that the raw multinomial logistic regression was overconfident on HIGH-risk predictions by ~8-10 percentage points — it predicted 85% probability when the empirical frequency was ~77%. After Platt scaling, ECE dropped from ~0.13 to 0.061. Calibration is critical here because the predicted probability is used as a routing key: overconfident HIGH predictions would route too many LOW-complexity blocks to Agentic RAG, wasting LLM budget.

---

**Q77. Pourquoi le DPLL(T) est efficace pour votre fragment Z3 ?**

DPLL(T) (Davis-Putnam-Logemann-Loveland with Theory solvers) is the backbone of modern SMT solving. For quantifier-free linear integer arithmetic (QF-LIA) — which covers all six CDAIS error class encodings — DPLL(T) uses the Simplex method as the theory solver and boolean SAT for the propositional backbone. This combination is complete and runs in polynomial time for linear arithmetic. Our constraint systems are small (≤20 integer variables per error class) and have no quantifiers or nonlinear terms, so DPLL(T) solves them in milliseconds. The `z3.Optimize` extension adds a minimization layer on top using the OMT (Optimization Modulo Theories) framework — still polynomial for linear objectives over linear arithmetic.

---

**Q78. Expliquez le Bayesian Model Averaging qui motive votre SemantiCheck composite score.**

Bayesian Model Averaging (BMA) says: when you have multiple models with different error profiles, their weighted combination achieves lower variance than any single model, provided the errors are not perfectly correlated. SemantiCheck's four layers are designed to be structurally orthogonal: L1 (Z3 formal proof) tests structural arithmetic correctness; L2 (behavioral oracle) tests output equivalence on adversarial data; L3 (CDAIS) tests class-specific semantic bug presence; L4 (LLM-oracle) tests approximate SAS semantic behavior. A translation could pass L1 (arithmetically correct structure) but fail L3 (has a RETAIN_RESET bug on multi-group data). The composite SCS captures what no single layer can. The BMA analogy motivates the weighted combination; the weights were set empirically on the gold-standard corpus.

---

**Q79. Qu'est-ce que la Reflexion dans votre translation agent ?**

Reflexion (from Shinn et al., 2023) is a prompting technique where the LLM critiques its own output and then tries to improve it. In Codara's TranslationAgent, Reflexion is triggered when cross-verification fails: the verifier LLM (Groq) says the primary translation has issues. The translation LLM receives: its original translation, the verifier's critique, and a Reflexion prompt asking it to identify what it did wrong and produce a corrected version. This is distinct from CEGAR repair (which gives a concrete counterexample) — Reflexion operates on natural language critique without a concrete failing input. Empirically, Reflexion resolves ~40% of cross-verification failures without needing to escalate to CEGAR.

---

**Q80. Qu'est-ce que le metamorphic testing et son rapport avec SemantiCheck ?**

Metamorphic testing verifies properties that should hold across related inputs — e.g., if you sort a dataset and then sort it again, the result should be the same. In SemantiCheck's oracle layer (L2), we apply metamorphic relations specific to SAS semantics: for a PROC SORT translation, sorting the input in two different ways and checking that both produce consistently ordered output; for a RETAIN translation, doubling all input values and verifying that the cumulative sum doubles too. This validates semantic properties without a ground-truth oracle for every possible input — the relation itself is the oracle. This is from Chen et al. (2018) and is the conceptual antecedent to MIS's confirmed invariants.

---

## LEVEL 6 — Trap Questions (What the Jury REALLY wants to probe)

---

**Q81. Votre rapport dit que vous avez eu un grade d'audit A-. C'est quoi les défauts qui ont empêché A+ ?**

Four rounds of security and code review with 44 fixes + 20 post-audit fixes. The main issues that prevented an A: (1) the ValidationAgent initially used `threading.Thread` for sandboxing — a security issue because threads can't be hard-killed on timeout, fixed to `multiprocessing.Process` with `.kill()`; (2) the Dockerfile had a broken `COPY config/` path after the rename from `sas_converter/` to `backend/`; (3) `config_manager.py` was writing to the source YAML at runtime, mixing read-only config with mutable state; (4) CORS was too permissive (wildcard). All were fixed. The A- reflects that these issues required multiple rounds to surface — a more experienced team would have caught them in review 1.

---

**Q82. En quoi votre approche est "neuro-symbolique" ? Ce terme est-il justifié ?**

Neuro-symbolic means combining neural (LLM-based, learned, statistical) components with symbolic (rule-based, formal, deterministic) components. In Codara: the FSM streaming parser, lark grammar, boundary detection rules, NetworkX graph, logistic regression complexity scorer, Z3 SMT solver, and CDAIS constraint encoding are symbolic. Only the TranslationAgent and ValidationAgent are truly neural — they use LLM reasoning. RAPTOR sits in between: GMM clustering is statistical but the summarization is LLM-based. The neuro-symbolic label is justified because the system deliberately deploys each type where it is most effective — LLMs where natural language understanding is irreplaceable (translation, repair), deterministic modules everywhere else (faster, cheaper, reproducible).

---

**Q83. Votre knowledge base a 330 paires — est-ce suffisant pour un système de production ?**

For a PFE, 330 verified pairs is a strong foundation. For Deloitte production, it's thin in specific categories: hash-object joins, complex WHERE-clause rewrites, multi-step PROC SQL with correlated subqueries are under-represented, and the translation accuracy for those constructs reflects it. The conclusion explicitly identifies KB expansion to 500+ targeted pairs as the highest-priority short-term action. The KB is designed to grow: the FeedbackIngestionAgent writes every human correction back to LanceDB automatically. At scale, Deloitte's own engineers correcting 10-20 translations per week would add ~500 pairs per month — the system has the infrastructure to exploit this.

---

**Q84. Est-ce que votre système peut être utilisé directement par Deloitte en production ?**

Not yet without three additions: (1) load testing beyond single-user scenarios — the Docker Compose stack has not been stress-tested; (2) connection pooling — SQLite in WAL mode is sufficient for development but PostgreSQL is needed for concurrent multi-user production; (3) secrets rotation — the current JWT secret and LLM API keys are env var based, which is fine for development but needs Azure Key Vault integration for production hardening (the Azure setup script exists but wasn't fully deployed). The architecture is production-oriented by design — containerized, monitored, with CI/CD. The gap is operational, not architectural.

---

**Q85. Vous avez utilisé 452 tests dans votre rapport final mais 248 dans l'article SCAM. Pourquoi la différence ?**

The paper was written before the final sprint weeks. At the SCAM submission point (mid-May 2026), the test count was 248 (36 CDAIS + 34 Z3 + core pipeline tests). By the report closure date (June 2026), 452 total tests were reported across 24 test files — including the CDAIS/MIS benchmark suite, Scenario A/B/C integration tests, and the expanded boundary detection test harness. The paper reports the count at submission time; the report reflects the final state. Both are honest counts of different moments.

---

**Q86. Quel est le coût LLM estimé par conversion ?**

Varies by complexity. A LOW-risk file (static RAG, short context, no repair): ~$0.01-0.03 using Azure GPT-4o-mini pricing. A HIGH-risk file with CEGAR repair (Agentic RAG, 8K token context, 2-3 CEGAR iterations): ~$0.15-0.40. The DuckDB audit log tracks every LLM call with token counts, latency, and cost estimate. The system minimizes cost by short-circuiting to deterministic rules for unambiguous constructs, using Groq's free tier for cross-verification, and using circuit breakers to avoid retrying failed expensive calls. The token budget per risk level (LOW: 2K, MOD: 4K, HIGH: 8K) is a hard cap enforced in the PromptManager.

---

**Q87. Comment gérez-vous les macros SAS ? C'est la vraie limite du système.**

Honestly: partially. The `CrossFileDepsResolver` detects macro call sites and resolves `%INCLUDE` links, so the pipeline knows which macro definition file to pull in. The `FileAnalysisAgent` extracts macro signatures (name, parameters, body) and stores them in the registry. When translating a partition that calls a macro, the Graph RAG retrieves the macro definition as context for the LLM. What we don't do: full macro pre-expansion — expanding `%apply_etl(input=raw, year=2024)` into the actual generated SAS code before boundary detection and translation. Without pre-expansion, the boundary detector sees the macro call (one line) not its expanded body (potentially 200 lines), which is why macro-heavy code has 52.1% F1 and the overall boundary detection missed the 90% target.

---

**Q88. Votre SemantiCheck utilise un "LLM-as-oracle" — n'est-ce pas circulaire ? Vous utilisez un LLM pour valider l'output d'un LLM.**

Fair challenge. The answer is: the LLM-oracle (L4) uses a *different* LLM (Groq LLaMA-3.3-70b) than the primary translator (Ollama minimax-m2.7:cloud), with a *different* prompt (not "translate this SAS" but "given this SAS code and this input, predict the expected output"). The two models have different training, different biases, and different error profiles. Empirically, they disagree on ~22% of cases, which is where L4 adds signal. It's not zero circularity — if both LLMs make the same systematic SAS semantics error, L4 gives a false pass. That's exactly why L4 is the *fourth* layer with the lowest weight in the SCS, not the primary verification signal. L1 (Z3), L2 (oracle), and L3 (CDAIS) are not LLM-based at all.

---

**Q89. Pourquoi vous n'avez pas fine-tuné un LLM spécifiquement sur SAS→Python ?**

The QLoRA fine-tuning notebook (`notebooks/fine_tune_qwen25_coder_sas.py`) exists and was prototyped for Qwen2.5-Coder on Google Colab T4. The blockers were practical: fine-tuning requires a large dataset of (SAS, Python) pairs with verified semantic equivalence — our 330-pair KB is too small to avoid overfitting, and scaling to 500+ was a Week 14 deliverable that extended into post-project work. A fine-tuned local model (LocalModel Tier 0 via llama-cpp) would eliminate Azure/Groq API costs and reduce latency — it's the highest-priority medium-term roadmap item. The architecture supports it: the llm_clients.py fallback chain already has a Tier 0 slot.

---

**Q90. Décrivez le scénario C complet — le cas le plus difficile de bout en bout.**

Scenario C: a 200-line SAS program with RETAIN-based BY-group running totals, a correlated PROC SQL subquery, and a macro `%DO` loop.

Pipeline path: `file_process` detects the cross-file macro dependency and registers it. `streaming` FSMs the 200 lines into tokens. `chunking` + lark grammar: the RETAIN block and PROC SQL block are detected as separate partitions (the macro block partially fails — boundary F1 = 52% on macros). `raptor` builds a cluster for "group accumulation patterns." `risk_routing`: ComplexityAgent scores HIGH (RETAIN + BY + macro references + PROC SQL subquery). `persist_index` writes to SQLite + NetworkX. `translation`: Agentic RAG with k=10 retrieves the most similar group-accumulation examples. LLM generates Python. Sandbox exec passes (code runs). Z3 finds a RETAIN_RESET counterexample (missing group reset). CEGAR repair loop: counterexample injected into repair prompt. LLM fixes the `groupby().cumsum()` to reset per group. Z3 re-verifies: UNSAT. CDAIS: RETAIN_RESET certificate issued. SemantiCheck SCS: VERIFIED. Total latency: ~45 seconds.

---

**Q91. Si votre jury vous demande de coder en live une partie du système, laquelle seriez-vous le plus à l'aise de démontrer ?**

Three choices: (1) the CDAIS Z3 encoding for RETAIN_RESET — I can write the constraint system from memory in ~20 lines of Python with z3-py; (2) the MIS Algorithm 2 in pure Python — it's a double loop over (corpus, candidates) with a simple counter; (3) the boundary detector deterministic rules — the lark grammar patterns for DATA step / PROC step / MACRO boundaries are concise and memorable. I would avoid live-coding the LangGraph orchestrator or the full translation pipeline — too many dependencies to set up.

---

**Q92. Quel aurait été votre plan B si Z3 ne fonctionnait pas sur votre type de contraintes ?**

We would have fallen back to bounded model checking (BMC) using CBMC or a Python-native tool like PyMC. The key insight is that our constraint systems are QF-LIA (quantifier-free linear integer arithmetic), which Z3 handles optimally. If Z3 had failed on our encodings (e.g., if we needed nonlinear arithmetic for certain SAS accumulations), the alternative would be to reformulate as integer linear programs (ILP) using PuLP or scipy.optimize — less elegant but still solvable for small witness sizes. The minimality objective would become a standard LP objective. In practice, Z3 worked well for all six error classes within the linear fragment.

---

**Q93. Citez 3 papers que vous avez lus et dites ce que vous en avez retenu pour votre travail.**

1. **Lewis et al. (2020), RAG (NeurIPS):** RAG's core insight — ground LLM generation in retrieved non-parametric knowledge — directly motivated the three-tier KB design. Key takeaway: retrieval quality matters more than generation quality for domain-specific tasks.

2. **Sarthi et al. (2024), RAPTOR:** Multi-level tree retrieval solves the compositional query problem of flat KNN. Key takeaway: cluster summaries complement leaf-level examples, not replace them — both should be in the index.

3. **Pan et al. (2024), ICSE — "Lost in Translation":** Systematic empirical study showing semantic errors (code that runs but produces wrong output) are the most frequent and hardest-to-detect bug class in LLM code translation. This is the direct empirical motivation for CDAIS — the paper shows the problem exists at scale; we built the solution.

---

**Q94. Si vous deviez recommencer, quelle serait la première chose que vous feriez différemment ?**

Build a complete SAS grammar parser with macro pre-expansion in Week 1, not a partial lark grammar retrofitted with an LLM fallback. Every downstream component — boundary detection, chunking, RAPTOR clustering, complexity scoring — would have been more accurate with correctly expanded macro content as input. The 79.3% F1 vs. 90% target gap and the 53.7% hard-tier translation gap both trace to this architectural decision. The partial grammar was a speed decision (lark + regex is fast to prototype) that created a technical debt that limited performance on the most important category of production SAS code.

---

**Q95. Quelle est votre contribution la plus originale, en une phrase ?**

CDAIS: using Z3's optimization modulo theories to synthesize formally minimal adversarial test inputs — 6 to 17 rows, synthesized in 73ms — that deterministically expose semantic migration bugs in LLM-generated code, with a soundness-proved coverage certificate scoped to structural shape, replacing unbounded random testing with a single guaranteed trial.

---

*Total: 95 questions across both parts — easy to lethal.*
*Must-know numbers: 72.4%, 96.8%, 79.3%, 53.7%, ECE=0.061, +12pp RAPTOR, 73ms CDAIS, 142 pairs MIS, 10/18 invariants, 330 KB pairs, 452 tests, 6/6 error classes.*
*Must-know by heart: Q9, Q13, Q26, Q27, Q59, Q63, Q95.*

---

## PART 3 — PhD-Level Jury Questions
*These professors have read your paper in detail, know the referenced works, and will try to find the seam between what you built and what you claim.*

---

### A — Statistical Validity Attacks

---

**Q96. Votre ablation RAPTOR utilise 50 queries. Est-ce statistiquement suffisant pour conclure un avantage de +12pp ?**

No, and the report acknowledges this implicitly. 50 queries give a 95% confidence interval of roughly ±14pp for a proportion (using Wilson interval on Hit-Rate@5), which means the true advantage could range from essentially zero to +26pp. We cannot claim statistical significance at p < 0.05. What we *can* claim: the measured effect size (+12pp) is in the direction predicted by the RAPTOR hypothesis, is consistent with the theoretical argument (cluster summaries help sparse queries), and exceeds the pre-specified target of ≥10pp. A properly powered study would need ~200 queries for a two-sided test at α=0.05, β=0.2 with the observed effect size. This is identified as future work.

---

**Q97. Vos résultats de traduction sont issus d'un seul run. Comment pouvez-vous en conclure quoi que ce soit ?**

The single-run limitation is stated explicitly in the evaluation chapter. The sources of variance are: LLM temperature (0.1, not 0.0 — not fully deterministic), API rate-limit induced fallback routing, and LanceDB ANN tie-breaking. Empirical observation across shorter benchmark runs suggests ±1-2pp variance on the overall success rate. So the 72.4% result sits in a range of roughly [70.4%, 74.4%] — which still clears the 70% target. The honest statement is: the point estimate is consistent with the target, but a multi-run study with mean ± standard deviation would strengthen the claim. We state this in Section 7.2.1. For a PFE with a four-month deadline and real API costs per run, this is a pragmatic constraint, not a methodological choice.

---

**Q98. Votre corpus MIS est annoté par un seul annotateur. Comment calculer l'incertitude sur les 10 invariants confirmés ?**

Without a second annotator, we cannot compute inter-rater reliability (Cohen's κ) directly. The defense is leave-one-out cross-validation: all 10 confirmed invariants remained confirmed in every fold (142/142 stability). LOO-CV provides a different form of robustness: it shows the confirmed set is not dependent on any single pair. The remaining uncertainty is systematic: if the single annotator made a systematic category error (e.g., consistently mis-labeling a pattern as correct SAS when it isn't), LOO-CV cannot detect it — only a second independent annotator could. This is precisely acknowledged in the Threats to Validity section. Future work: double annotation on 30-50 pairs with measured κ.

---

**Q99. Votre ECE est calculé sur 66 partitions (20% split de 330). Le split est-il stratifié par risk level ?**

The split was stratified to maintain the risk-level distribution (36% LOW, 41% MOD, 18% HIGH, 5% UNCERTAIN). Without stratification, a random 20% split on 330 pairs could produce a validation set with, say, 25% HIGH-risk partitions — overrepresenting the hardest class and inflating the measured ECE. The `CalibratedClassifierCV` in scikit-learn was used with `cv=5` and `method='sigmoid'`, which uses stratified k-fold internally. The reported ECE = 0.061 is on the outer held-out split, not the calibration split, to avoid optimistic bias.

---

**Q100. Vos métriques RAPTOR (Hit-Rate@5 et MRR) utilisent quelle définition de "relevance" ? C'est subjectif ?**

Relevance is defined operationally as: the retrieved KB entry's `category` field matches the query partition's `partition_type` (DATA_STEP, PROC_SORT, PROC_SQL, MACRO_DEF, etc.). This is not human-judged relevance — it's an automatic label match. The limitation is that two DATA steps can be semantically very different (a simple assignment vs. a RETAIN accumulator), and the category label doesn't distinguish them. True relevance would require human judgement per (query, result) pair, which is expensive. The operational definition is reproducible and automatic but underestimates true relevance for fine-grained distinctions within a category. This is why the downstream metric (translation success rate) is reported alongside Hit-Rate@5 — it provides a functional measure of retrieval quality's practical impact.

---

### B — Formal Methods Deep Probes

---

**Q101. Votre théorème de soundness (Theorem 1) — les hypothèses sont-elles réalistes ? La preuve par contraposée est-elle complète ?**

The proof has two steps: (1) the witness W satisfies the divergence constraint δ_C by construction (Z3 returned SAT on δ_C); (2) if B_C(p) = 1 (the translation has the bug), then f_bug(W) ≠ f_oracle(W) by the encoding design. Step 2 is the critical assumption: it requires that the Z3 constraint δ_C is a *necessary and sufficient* encoding of the divergence condition for class C. This is justified per error class by construction — for RETAIN_RESET, the divergence simplifies to a single inequality (C_{0,R-1} ≠ 0) that any positive-valued input satisfies, and the encoding captures this exactly. Where the theorem is not complete: the mapping from Python code to f_bug requires identifying which Python computation path is executed, which is not formally encoded — we assume the structural pattern (e.g., `df.cumsum()` without `groupby`) unambiguously maps to f_bug. This is an assumption about the translation's syntactic form, not its semantics.

---

**Q102. La couverture certificate est "scoped to structural shape". Qu'est-ce que ça signifie formellement ? C'est une garantie faible.**

Yes, it is intentionally weak — and that is stated explicitly. The formal scope is: for all datasets D with exactly the same (n_groups × n_rows_per_group) structure as the witness W, the translation is free from class C. This does not cover: (a) datasets with more groups, (b) datasets with more rows per group, (c) datasets with a different value range (though the linear arithmetic encoding means value range generalization holds within v_min ≤ v ≤ v_max). The reason for this scoping: providing a certificate for all possible shapes would require universal quantification over all shapes, which is undecidable. The structural scope is the largest decidable fragment we can certify. Practically, the CDAIS witness is generated with the same structural shape as the production data's expected group/row distribution, which makes the certificate applicable in context.

---

**Q103. Est-ce que le problème d'optimisation Z3 (z3.Optimize avec minimize) est toujours polynomial pour vos encodings ?**

For quantifier-free linear integer arithmetic (QF-LIA) with a linear objective, Optimization Modulo Theories (OMT) is polynomial in the size of the formula — it reduces to a sequence of linear programs (Simplex calls) guided by the DPLL(T) backbone. The catch: QF-LIA satisfiability itself is NP-complete in general (it reduces to integer programming). However, our constraint systems have a specific structure: the number of integer variables is O(G×R) (groups × rows), bounded at ≤17 for all six error classes. For a fixed, small number of variables, ILP is polynomial in the number of constraints. In practice, Z3 solves all six encodings in under 300ms — consistent with the polynomial behavior for small instances. The SORT_STABLE 296ms case is the worst because the strict ordering constraint ($s_0 < s_1 < \cdots < s_{16}$) on 17 variables involves more Simplex iterations than the sum-equality constraints of the other classes.

---

**Q104. La boucle CEGAR est-elle guaranteed to terminate ?**

No — and this is a standard limitation of CEGAR loops in practice. The loop terminates in two cases: (1) Z3 returns UNSAT (the repaired translation is verified), or (2) the iteration budget is exhausted (set to 3 iterations in the implementation). Without the budget, the loop could theoretically cycle: the LLM produces a repair, Z3 finds a new counterexample, the LLM produces another repair that reintroduces the original bug, etc. The budget is a pragmatic termination guarantee, not a theoretical one. For a theoretical guarantee, you would need the LLM repair to be provably monotone (each repair brings the translation closer to correct) — which cannot be guaranteed for a probabilistic generative model. The empirical observation: 43 errors were fixed in the evaluation run with 0 cycles observed, but this is not a proof.

---

**Q105. Votre preuve du Théorème 1 dit "f_oracle(W) = sem_oracle(s, W)". Comment savez-vous que votre oracle Python est fidèle à SAS ?**

This is the oracle correctness assumption — the most vulnerable point of the formal argument. The oracle functions were validated against SAS 9.4 Language Reference §§ covering RETAIN, LAG, PROC SORT, SUM function, MERGE join types, and FIRST./LAST. semantics. They were also unit-tested with 36 CDAIS-specific tests. But: they were not validated against a running SAS 9.4 instance because we don't have a SAS license. The validation is therefore: (a) manual cross-checking against the formal SAS specification document, and (b) the self-consistency argument that rejected invariants (like LAG_NULL_FIRST_ROW at 0% oracle pass rate) reveal oracle errors, which we then corrected. This is a limitation of the threat to construct validity — acknowledged in Section 6.2. A future version with a SAS cloud instance for ground truth would close this gap.

---

### C — Information Retrieval & Embedding Theory

---

**Q106. Pourquoi cosine similarity et pas dot product ou L2 distance pour votre retrieval LanceDB ?**

Cosine similarity measures the angle between two vectors, normalized by their magnitudes — it is invariant to vector length. Dot product is not length-invariant: a long vector (from a long SAS snippet with many tokens) would dominate short vectors even if the semantic content is less similar. L2 distance penalizes both direction and magnitude differences. For sentence embeddings where document length varies significantly (SAS partitions range from 5 to 200+ lines), cosine similarity is the appropriate metric. Nomic Embed v1.5 was specifically trained with cosine similarity as the objective (contrastive learning with cosine loss), so using dot product without normalization would violate the embedding model's assumptions.

---

**Q107. Qu'est-ce que l'indexage IVF (Inverted File Index) dans LanceDB ? Quelle est sa complexité ?**

IVF partitions the embedding space into K Voronoi cells (clusters) using K-means. At index time, each vector is assigned to its nearest cluster centroid (O(K×d) per vector, O(N×K×d) total). At query time, the nprobe nearest centroids are identified (O(K×d)), then only vectors in those nprobe cells are scanned exactly (O(nprobe × N/K × d)). Total query complexity: O(K×d + nprobe×N/K×d) vs. O(N×d) for exact search. With K=100, nprobe=10, N=330, d=768: IVF scans ~33 vectors per query vs 330 for brute force — roughly 10× faster. For 330 pairs, the speedup is marginal; IVF pays off at N > 10,000. We use IVF for architectural consistency — as the KB grows toward 500+ pairs and eventually thousands, the index remains efficient without redesign.

---

**Q108. GMM pour le clustering RAPTOR — pourquoi pas K-means ? Et comment choisir le nombre de composantes ?**

K-means produces hard cluster assignments (each point belongs to exactly one cluster). GMM produces soft assignments (each point has a probability of belonging to each cluster) — more appropriate for code partitions that genuinely sit at the intersection of multiple pattern categories (e.g., a RETAIN + PROC SQL hybrid). GMM also estimates the covariance structure of each cluster (full, tied, diagonal, or spherical), capturing that some clusters are more elongated or anisotropic than others in embedding space. The number of components G is selected by minimizing BIC (Bayesian Information Criterion) on the embedding set: BIC penalizes model complexity, preventing over-segmentation. In practice, with 330 pairs and 768-dim embeddings (PCA-reduced to 50 dims before GMM for tractability), BIC typically selects G ∈ [8, 15] clusters. RAPTOR skips GMM if n_partitions < 2.

---

**Q109. HNSW vs IVF pour le vector index — pourquoi vous n'avez pas utilisé HNSW ?**

HNSW (Hierarchical Navigable Small World) is a graph-based ANN algorithm with O(log N) query complexity and excellent recall/speed tradeoff for large N. IVF is cluster-based with O(√N) effective query complexity. For N=330, the practical difference is negligible — both return results in milliseconds. We chose IVF because LanceDB's native index is IVF-PQ (IVF with product quantization), which is the default optimized path in LanceDB v0.22, well-documented, and battle-tested. HNSW would require a different library (FAISS or hnswlib) and an additional dependency. The principle: don't add complexity without a measurable benefit. If the KB scales to 100K+ pairs, HNSW becomes the right choice.

---

### D — Software Engineering Research

---

**Q110. DSR exige que le chercheur "rigorously evaluate" l'artefact. Avec un seul run et sans test statistique, êtes-vous conforme aux guidelines de Hevner 2004 ?**

Partially. Hevner et al.'s Guideline 3 (Design Evaluation) requires "rigorously evaluating the utility, quality, and efficacy of a design artifact." The rigor criteria include: observational (case study, field study), analytical (static analysis, formal proof), experimental (controlled experiment, simulation), testing (functional, structural), and descriptive (informed argument, scenarios). We provide: formal proofs (Z3 UNSAT certificates, Theorem 1 soundness), experimental evaluation (gold-standard corpus, ablation study), descriptive scenarios (A, B, C), and analytical evaluation (ECE calibration, LOO-CV). What we lack: controlled multi-run experiments with significance tests. Hevner 2004 does not mandate statistical significance as a requirement — it lists observational and descriptive methods as valid. However, a stronger claim would require multi-run evidence. The honest position: we meet Hevner's minimum criteria, but a journal extension would strengthen Guideline 3.

---

**Q111. Votre contribution "MIS is the first corpus-driven migration invariant validation framework" — comment pouvez-vous affirmer "first" ?**

A "first" claim requires a literature search thorough enough to rule out prior work. Our search covered: ACM Digital Library, IEEE Xplore, and Semantic Scholar for terms "migration invariant", "translation invariant", "legacy code migration specification", "SAS Python migration verification", and combinations thereof. The closest work — Daikon (Ernst et al. 2001) — discovers invariants from single-program traces, not pairs. The Oracle problem literature (Barr et al. 2015) covers test oracles but not paired corpus-based invariant confirmation. Metamorphic testing (Chen et al. 2018) tests properties of single programs, not migration pairs. We found no work that: (a) takes an analyst-provided candidate library, (b) confirms candidates against oracle-validated (source, target) pairs, (c) produces a reusable invariant specification for checking future translations. The "first" claim is defensible given this search, with the standard caveat: absence of evidence is not evidence of absence.

---

**Q112. Qu'est-ce que le "construct validity threat" que vous mentionnez dans votre paper ?**

Construct validity asks: does your measurement instrument actually measure what you claim it measures? Our threat: SemantiCheck (SCS) measures semantic equivalence on adversarial synthetic data generated by DummyDataGenerator, not on real production SAS inputs. If DummyDataGenerator systematically fails to generate the distribution of inputs that occur in practice (e.g., it generates only integer values but real data contains nulls and strings), then SCS on synthetic data does not predict SCS on production data. Our mitigation: DummyDataGenerator is specifically designed to cover the failure modes — it injects NaN values, multiple groups, exact duplicates, and currency strings that match the six error class triggers. But it is not a sample from the true production input distribution. This limits the external construct validity of SCS as a predictor of production-time correctness.

---

**Q113. Pourquoi logistic regression et pas un modèle plus puissant (Random Forest, SVM, ou même un LLM) pour le complexity scorer ?**

Three reasons. (1) Calibration: logistic regression produces well-calibrated probabilities by design — its loss function (log-loss / cross-entropy) directly optimizes for calibration. Tree-based models and SVMs are not natively calibrated and require post-hoc calibration (Platt scaling or isotonic regression). (2) Sample size: with 330 training pairs and 18 features, a Random Forest with hundreds of trees would overfit severely (p >> n regime effectively, given high-dimensional feature interactions). Logistic regression's built-in L2 regularization provides appropriate inductive bias. (3) Interpretability: the learned coefficients directly expose which features drive HIGH-risk predictions — this is valuable for debugging and explaining routing decisions to Deloitte engineers. An LLM for complexity scoring would add 5-30 seconds latency per partition for a task that logistic regression handles in <1ms.

---

**Q114. Votre système utilise une "3-tier RAG" — mais qu'est-ce qui justifie exactement 3 tiers et pas 2 ou 4 ?**

The three tiers correspond to three distinct retrieval capabilities that cannot be merged without loss. Static RAG (Tier 1) does leaf-level KNN — appropriate when the partition is self-contained and similar examples exist. Graph RAG (Tier 2) adds dependency-graph traversal — necessary when the partition calls external macros or references cross-file datasets; KNN alone cannot retrieve this context because the macro definition is not similar to the current partition, only *linked* to it. Agentic RAG (Tier 3) adds iterative query refinement — necessary when no single query covers all sub-constructs of a complex partition and multiple targeted retrievals are needed. You cannot collapse Tier 2 into Tier 1 (KNN doesn't follow graph edges) or Tier 2 into Tier 3 (graph traversal doesn't iterate). A fourth tier (e.g., a fine-tuned retriever) would require a labeled query-relevance dataset that doesn't exist yet. Three tiers is the minimum that covers all three fundamentally distinct retrieval needs.

---

### E — LLM Theory

---

**Q115. Qu'est-ce que l'"hallucination" dans un LLM, formellement ? Comment la RAG la réduit-elle ?**

Formally, hallucination arises from the LLM learning a distribution P(output | prompt) that is high-probability for fluent, plausible text even when that text is factually incorrect. The model maximizes likelihood over the training distribution; if correct SAS translations are rare in pre-training data (which they are — SAS is not widely represented in public code corpora), the model fills gaps with statistically likely Python patterns (e.g., `df.cumsum()`) that are correct for simpler cases but wrong for the specific SAS construct. RAG reduces hallucination by conditioning the generation on retrieved evidence: P(output | prompt, retrieved_examples). The retrieved examples shift the conditional distribution toward patterns that are empirically correct for the specific construct. This is the grounding effect — empirically measured as a reduction in RETAIN_RESET errors when relevant examples are retrieved.

---

**Q116. La cross-verification par un LLM indépendant — sur quelle théorie vous basez-vous pour affirmer que deux LLMs sont "indépendants" ?**

Independence here means statistical independence of errors, not logical independence. Two LLMs trained on different data with different architectures will have different error distributions — they are unlikely to make the same mistake on the same input. We use minimax-m2.7:cloud as the primary translator and Groq LLaMA-3.3-70b as the verifier. These have different training corpora, different parameter counts, and different RLHF preferences. The theoretical basis: ensemble methods (bagging, stacking) work because diverse models' errors are not perfectly correlated. We are applying this principle without claiming statistical independence — we claim *diverse enough* that their agreement on a translation is stronger evidence of correctness than either alone. The limit: if both models share a systematic bias from similar pre-training data (e.g., both trained on the same public Python codebases that handle SAS RETAIN incorrectly), cross-verification would miss that class of error. CDAIS exists precisely for this case.

---

**Q117. Votre prompt engineering — vous utilisez Jinja2 templates. Comment évitez-vous le "prompt injection" dans les SAS inputs ?**

SAS code injected into the prompt through user-uploaded files could potentially contain text that looks like prompt instructions (e.g., a SAS comment containing "ignore previous instructions"). The mitigations: (1) SAS source code is placed in a clearly delimited code block in the Jinja2 template — `<SAS_CODE>...</SAS_CODE>` tags — which most modern LLMs respect as content boundaries; (2) the PromptManager sanitizes non-printable characters and truncates to the token budget before template rendering; (3) the structured output constraint (instructor/Pydantic model) means the LLM's response must parse as a valid `TranslationOutput` object — injection that produces free-form text would fail the Pydantic validation and trigger a retry. This is defense-in-depth, not a formal proof against prompt injection.

---

### F — Systems & Security

---

**Q118. Pourquoi HS256 pour JWT et pas RS256 ou ES256 ?**

HS256 (HMAC-SHA256) uses a shared symmetric secret — both the signer and the verifier use the same key. RS256 uses RSA asymmetric keys — the private key signs, the public key verifies. For a single-server deployment (one FastAPI instance both issues and verifies tokens), HS256 is simpler, faster (no asymmetric crypto overhead), and equally secure given a strong secret. RS256 is necessary when multiple services need to verify tokens independently without access to the signing secret (microservices, API gateways). In Codara's current architecture, all JWTs are issued and verified by the same FastAPI instance — HS256 is the correct choice. If Deloitte deploys a microservices architecture where a separate auth service issues tokens to be verified by multiple backend services, RS256 would be mandatory.

---

**Q119. Votre sandbox exec() supprime les builtins — mais un attaquant peut-il quand même s'échapper ?**

The sandbox removes `__import__`, `open`, `exec`, `eval`, `compile`, and system interaction builtins. Known bypass vectors: (1) via `__class__.__bases__[0].__subclasses__()` — traversing Python's MRO to find loaded modules. Mitigation: the sandbox also restricts `__class__`, `__bases__`, and `__subclasses__` access by removing `__builtins__` entirely and providing a restricted namespace. (2) Via already-imported modules in the exec scope — if pandas is imported before the exec, the translated code can use `pd.read_csv()` for file access. Mitigation: the namespace passed to exec() contains only the specific imports needed for the translation (numpy, pandas with specific methods whitelisted). (3) Timing attacks that exhaust memory before the process kill. Mitigation: `multiprocessing.Process` is killed hard with `.kill()` on timeout. No sandbox is perfectly secure — this is defense in depth, not a formal isolation guarantee.

---

### G — The Hardest Questions (PhD Signature Attacks)

---

**Q120. Votre work claims "formally grounded" — mais MIS ne fournit aucune preuve formelle. Pourquoi ce terme dans le titre ?**

The paper uses "formally grounded" deliberately and precisely — not "formally proven." CDAIS is formally grounded in Z3 SMT constraints and a proven soundness theorem. MIS is formally grounded in a corpus-validated selection algorithm with LOO-CV stability. The word "formal" in "formally grounded" modifies the *method* (constraint-based synthesis for CDAIS, corpus-based selection with statistical validation for MIS), not the *conclusion* (which for MIS is empirical, not a proof). Contrast with "heuristic": heuristic testing has no formal structure — it generates random data and observes outputs. Both CDAIS and MIS have explicit formal structure (Z3 constraint systems and an algorithm with a defined correctness criterion). The title accurately scopes the claim; "formally proven" would be a stronger and incorrect characterization.

---

**Q121. Votre système est un "accelerator" — mais si le meilleur SCS que vous atteignez est 0.552 sur le torture test, est-ce que les data engineers font confiance aux résultats ?**

SCS = 0.552 on the torture test is the *worst-case* average — the torture test was designed to defeat the system. On the full 721-block gold corpus, the average SCS is 0.67, with LOW-risk blocks averaging 0.81. In practice, a data engineer does not work with SCS as a binary pass/fail. The system provides: (1) a structured SemantiCheck report per block showing which layers passed and which failed; (2) a CDAIS report naming which error classes were found or certified; (3) side-by-side diff view in the frontend. The data engineer's workflow is: accept HIGH-SCS blocks automatically, manually review UNCERTAIN/LIKELY_INCORRECT blocks with the specific failure diagnosis. The accelerator's value is not "trust all output blindly" — it is "reduce manual review to the 30% of blocks that genuinely need it, with a precise diagnosis of what to fix."

---

**Q122. RAPTOR utilise GMM sur des embeddings 768-dim — avez-vous vérifié que GMM converge avec ces dimensions ? Le "curse of dimensionality" s'applique-t-il ?**

The curse of dimensionality does affect GMM in high dimensions: distance concentrates (all pairwise distances become similar), making Gaussian assumptions about cluster shape unreliable. Our mitigation: we apply PCA reduction to 50 dimensions before GMM (preserving ~85% of variance for our KB). At 50 dimensions, distance concentration is much less severe and GMM's Gaussian assumptions are more defensible. We verified convergence empirically: the EM algorithm converged in <20 iterations for all 8-15 component configurations on the 330-pair KB. A more principled approach would use a Dirichlet Process GMM (infinite GMM) or a VAE to learn a more compact latent space — both are valid future improvements. The current approach is justified by the small KB size (330 pairs) where even a crude clustering significantly improves retrieval over flat KNN.

---

**Q123. Votre conclusion dit "the architecture is not specific to SAS" — mais CDAIS encode des contraintes spécifiques à SAS (RETAIN, LAG, PROC SORT). Comment généralisez-vous ?**

The CDAIS *framework* generalizes; the specific *constraint encodings* do not. Generalization requires re-specifying: (1) a new error class taxonomy for the target language pair (e.g., COBOL→Java: pointer arithmetic bugs, signed/unsigned overflow, PERFORM paragraph semantics); (2) new Z3 constraint encodings for each class; (3) new oracle functions implementing the source language semantics. The framework (Algorithm 1: encode → optimize → extract → certify) is language-agnostic. The CDAIS paper's contribution is the framework and the proof that the soundness theorem holds for any constraint encoding that satisfies the divergence condition — not the specific six SAS encodings. MIS generalizes similarly: change the candidate invariant library and the oracle functions. The architecture's language-agnosticism fell out naturally from separating the framework from its instantiation; we confirm this by showing all three layers (Z3, CDAIS, MIS) have clear interfaces where language-specific logic plugs in.

---

**Q124. Votre paper cite Pan et al. 2024 (ICSE) comme motivation directe. Mais Pan et al. étudient 6 language pairs — pas SAS→Python. Est-ce que leur taxonomy s'applique à votre cas ?**

Pan et al.'s taxonomy covers general LLM translation bugs across Java↔Python, C++↔Python, etc. Their most prevalent bug categories include: type conversion errors, library API mismatches, off-by-one errors, and semantic differences in control flow. Our six SAS-specific error classes overlap with their framework at a high level (RETAIN_RESET maps to their "semantic equivalence" class; JOIN_TYPE maps to "library API mismatch") but are not identical — they don't study SAS at all. We cite Pan et al. for the general finding that "semantic errors are the most frequent and hardest-to-detect class in LLM code translation" — that claim is language-pair independent and directly motivates CDAIS. We do not claim our taxonomy *is* their taxonomy. The SAS-specific classes were derived independently from the 330-pair Codara corpus. The citation is motivation, not instantiation.

---

**Q125. Si vous pouviez soumettre ce travail à ICSE plutôt que SCAM, que changeriez-vous ?**

Three things for ICSE's rigor bar: (1) multi-run evaluation with mean ± standard deviation and statistical significance tests (Wilcoxon signed-rank or bootstrap confidence intervals) for every comparison — ICSE reviewers will reject a single-run comparison for claims at this level; (2) a second independent annotator for the VTP corpus with a measured Cohen's κ ≥ 0.80 to strengthen the MIS corpus validation; (3) generalization experiments — applying CDAIS and MIS to at least one additional migration pair (SAS→PySpark or COBOL→Java) to demonstrate that the framework is not SAS-specific. The current paper is appropriately scoped for SCAM (a focused venue on source code analysis and manipulation); the ICSE version would require 6 more months of experiments. The SCAM submission is the right first venue for establishing the core technical claims before scaling the evaluation.

---

*Total: 125 questions — Part 3 targets PhD-level IT professors specifically.*
*The PhD jury's 5 favorite traps: Q96 (statistical sufficiency), Q101 (proof completeness), Q110 (DSR rigor), Q120 ("formally grounded" title defense), Q121 (SCS 0.552 trust).*
*Answer these with honesty + structure: state what the limitation is, state what evidence you have anyway, state what future work closes the gap. Never defend a weakness — acknowledge it and pivot to what you did.*

---

## PART 4 — Deep Paper Dissection
*Every number, every claim, every table, every rejected invariant. This is what a professor who read your paper the night before will ask.*

---

### A — The Five Definitions (They Will Ask You to Recite Them)

---

**Q126. Donnez-moi la définition formelle d'une "migration correcte" (Définition 1) et expliquez chaque symbole.**

Definition 1: Let s ∈ S be a SAS code block and P the space of Python programs. A migration function M: S → P is *correct* if for all inputs D: sem_SAS(s, D) ≈ sem_Py(M(s), D), where ≈ is behavioral equivalence up to column naming and ordering.

- **s**: a single SAS code block (DATA step, PROC step, or macro fragment) — not a whole file
- **S**: the space of all syntactically valid SAS blocks
- **P**: the space of all Python programs (including incorrect ones)
- **M**: the LLM — it maps SAS text to Python text
- **D**: any concrete input dataset (a DataFrame in practice)
- **sem_SAS(s, D)**: the output SAS would produce by running s on D
- **≈**: not strict equality — we allow column rename and row reordering because SAS and pandas have different default behaviors on column order and sort stability

The "for all D" is what makes this undecidable in general (Rice's theorem). CDAIS provides partial evidence for specific shapes D; Z3 provides full evidence for encodable patterns.

---

**Q127. Définition 2 — "Semantic Error Class". C'est quoi P_C et B_C ? Donnez un exemple concret pour RETAIN_RESET.**

A Semantic Error Class C is a pair (P_C, B_C):
- **P_C: S → {0,1}**: applicability predicate — identifies SAS blocks where this class *can* apply. For RETAIN_RESET, P_C(s) = 1 iff s contains `RETAIN` with `BY` and `FIRST.`
- **B_C: P → {0,1}**: bug predicate — identifies the erroneous Python pattern. For RETAIN_RESET, B_C(p) = 1 iff p uses `cumsum()` without a `groupby()` reset

A translation p = M(s) exhibits class C iff P_C(s) = 1 AND B_C(p) = 1. In plain terms: the SAS code has the construct, and the Python code has the wrong pattern for it. Both conditions must hold simultaneously — there's no error if the SAS doesn't use RETAIN (P_C = 0) or if the Python correctly resets per group (B_C = 0).

---

**Q128. Définition 3 — "Witness". Qu'est-ce que la "structural shape D" signifie exactement ? Pourquoi vous la paramétrez ?**

A witness W is a concrete input DataFrame such that sem_oracle(s, W) ≠ sem_Py(p_bug, W) — it makes the divergence visible. The structural shape D = n_groups × n_rows_per_group parameterizes the witness. We parameterize because: the divergence condition depends on the data structure, not just the data values. For RETAIN_RESET, you need at least 2 groups — with 1 group, cumsum() and groupby().cumsum() agree. The shape (G=2, R=3) is the minimum that makes the divergence appear. The certificate is then scoped to this shape: "this translation is free from RETAIN_RESET for any 2-group, 3-row-per-group dataset." This is more precise than saying "for any dataset" (untrue) or "only for this exact witness" (too weak).

---

**Q129. Définition 4 — Coverage Certificate. Expliquez pourquoi c'est une guarantee et non pas juste un test qui a passé.**

A standard test that passes says: "this specific input did not expose a bug." A coverage certificate says something stronger: "this translation is *free from class C* for *all* datasets of structural shape D." The difference comes from the constraint encoding. The witness W was synthesized by Z3 to satisfy δ_C — the necessary and sufficient divergence condition for class C. If the translation passes W (oracle = translation on W), then the bug predicate B_C(p) = 0 — proven by contrapositive (Theorem 1). Any other dataset D' of the same shape that exhibits the bug would also be a satisfying assignment of δ_C, and therefore would produce the same divergence on W. So passing W implies passing all D' in the same shape class. This is the gap between a test (one input) and a certificate (all inputs of a class).

---

**Q130. Définition 5 — Migration Invariant. Quelle est la différence avec un "program invariant" classique ?**

A classical program invariant (Hoare logic sense) is a property that holds at a specific point in a single program's execution for all inputs — e.g., "at this loop checkpoint, count ≥ 0." A migration invariant φ is a property of *two* executions — the oracle output and the translation output — for a specific SAS pattern: φ(input(s), oracle(s)) = 1. It is a property of the *relationship* between SAS behavior and Python behavior, not of either program in isolation. Furthermore, a migration invariant is confirmed empirically (corpus-based) rather than proven logically. The oracle violations = 0 criterion means every correct SAS execution in the applicable corpus satisfies φ — it is an *empirically universal* property of correct migration, not a logically proven one.

---

### B — The Algorithms Line by Line

---

**Q131. Lisez-moi Algorithm 1 (CDAIS) étape par étape. Que se passe-t-il si Z3 retourne UNSAT ? Et si timeout ?**

Algorithm 1 step by step:
1. Create `z3.Optimize()` instance — an optimization-capable SMT solver (unlike plain `z3.Solver`, it can minimize objectives)
2. Set timeout — hard wall clock limit per synthesis attempt
3. `C.encode(opt, config)` — add all δ_C constraints to the optimizer; this mutates `opt` by calling `opt.add(constraint)` for each divergence formula; returns symbolic variable handles
4. Extract integer variables from the symbolic encoding — these are the witness values we want to minimize
5. `opt.minimize(sum(int_vars))` — add the minimality soft objective; Z3 will find the *smallest* satisfying assignment
6. `opt.check()` — invoke the solver; this is the expensive step (up to timeout)
7. If UNSAT: return ∅ — the divergence is *impossible* for the given config (e.g., config G=1 for RETAIN_RESET — with one group, no divergence exists). We would then try a larger config.
8. Extract model: `opt.model()` returns a satisfying assignment mapping each symbolic variable to a concrete integer
9. `model_to_dataframe(model, encoded)` — materialize the assignment into a pandas DataFrame using the column structure defined in `encoded`
10. Return W — the witness DataFrame

If timeout: return ∅, log as `synthesis_timeout`, skip CDAIS for this class. The class is not certified but also not failed — it simply gets no certificate. This happened 0 times in the benchmark for the six classes.

---

**Q132. Algorithm 2 (MIS) — pourquoi "oracle_violations = 0" et pas "actual_violations = 0" comme critère de confirmation ?**

This distinction is the core insight of MIS. Two different things can violate an invariant:

- **oracle_violations > 0**: the SAS oracle itself violates the invariant. This means the invariant is *not a real property of SAS semantics* — SAS doesn't always satisfy this property. The invariant is rejected because it's wrong about what SAS does.

- **actual_violations > 0**: the Python translation violates the invariant, but the oracle doesn't. This means the translation has a bug — it breaks a property that correct SAS output always satisfies.

The confirmation criterion `oracle_violations = 0` selects invariants that are genuinely true of SAS output for all applicable pairs. Once confirmed, `actual_violations > 0` on a new translation is a semantic error signal. If we used `actual_violations = 0` as the criterion, we'd confirm invariants that are accidentally satisfied by the current translations — not properties of SAS semantics.

---

**Q133. Dans Algorithm 2, que se passe-t-il avec GROUP_BOUNDARY_STRICT_SUBSET qui a 0 applicable pairs ?**

Its status is "not applicable" — neither confirmed nor rejected. The applicability predicate `φ_j.pattern matches s_i` returned false for every pair in the 142-pair VTP corpus. This means none of the 142 SAS programs use the specific FIRST./LAST. pattern in a way that would trigger this invariant's check. It's not a rejection (which requires at least one oracle violation); it's a coverage gap. The invariant may be perfectly valid but simply untestable with the current corpus. This is different from LAG_NULL_FIRST_ROW (applicable to 2 pairs, 0% oracle pass — a genuine rejection). GROUP_BOUNDARY_STRICT_SUBSET needs more enterprise SAS examples that use FIRST./LAST. in the specific way the invariant targets.

---

### C — Every Number in the Paper Explained

---

**Q134. "Average 7.8 rows" — recalculate it from the per-class witnesses.**

From Table 2: RETAIN_RESET = 6 rows, LAG_QUEUE = 6 rows, SORT_STABLE = 17 rows, NULL_ARITHMETIC = 6 rows, JOIN_TYPE = 6 rows, GROUP_BOUNDARY = 6 rows. Average = (6+6+17+6+6+6)/6 = 47/6 = 7.83 ≈ 7.8 rows. SORT_STABLE dominates because of the numpy introsort threshold requiring 17 equal-key rows. Without SORT_STABLE, the average would be 6.0 rows — the minimality objective always finds the same 2-group × 3-row minimum for the five linear arithmetic classes.

---

**Q135. "~75% PTDR for random testing" — pourquoi pas 100% avec 200 trials si le witness n'a que 6 rows ?**

Because random testing doesn't know what to look for. Generating 200 random DataFrames of 2-1000 rows with random values: most will be single-group datasets (where cumsum() and groupby().cumsum() agree), or will have values where both computations happen to produce the same result. For RETAIN_RESET, you need at least 2 groups with non-zero values in group 0 — the probability that a random 2-80 row dataset satisfies this is roughly 72.5% (observed). For SORT_STABLE, you need ≥17 rows with equal primary keys — far less likely in random generation, hence 25.5% PTDR. The heuristic baseline (which enforces ≥2 groups by construction) jumps to 100% for RETAIN_RESET — it gets the structural requirement right but still fails at 46% for SORT_STABLE because it doesn't know about the 17-row threshold.

---

**Q136. "confidence ≥0.65" pour la validation cross-provider des 12 VTP pairs — pourquoi ce seuil ?**

The 12 cross-provider verified pairs were validated by Groq LLaMA-3.3-70b acting as an equivalence checker: given both the SAS source and the Python translation, it outputs a confidence score (0-1) for "these are semantically equivalent." 0.65 was chosen as the threshold after calibration: at 0.65, the LLM's equivalence judgement agreed with manual review on 11/12 of a pilot set; below 0.65, agreement dropped to ~70%. The threshold is a pragmatic cutoff, not a theoretically derived one. Pairs that passed 0.65 LLM confidence *and* manual review are included; either failing alone excludes the pair. The 130 enterprise pairs bypassed this threshold — they were validated by a human expert directly.

---

**Q137. "Total MIS runtime: 937ms" — détaillez ce chiffre. C'est pour quoi exactement ?**

937ms is the total wall-clock time to run Algorithm 2 on the full 142-pair VTP corpus with all 18 candidate invariants on CPU (Intel i7, no GPU). The breakdown: for each of 142 pairs, generate adversarial input with DummyDataGenerator (~2ms), run oracle (~3ms), run translation exec (~5ms), check all 18 invariants (~1ms each) = ~28ms per pair. 142 × 28ms ≈ 3.9 seconds for serial execution. The actual 937ms suggests parallel execution across pairs (asyncio.gather over the 142 pairs, CPU-bound work in threads). Note: this does not include LLM calls — the 142 oracle executions use the Python oracle functions, not an LLM. LOO-CV runtime (12.1s) is 13× higher because it runs Algorithm 2 142 times (once per fold) ≈ 142 × 937ms / parallel_factor.

---

**Q138. Pourquoi le heuristic baseline a 100% sur RETAIN_RESET mais CDAIS l'obtient aussi — quelle est la vraie différence ?**

Both achieve detection on RETAIN_RESET. The difference is: the heuristic generates ~30 rows and happens to create 2+ groups by construction (it enforces ≥2 groups as a rule). For RETAIN_RESET, 2 groups with any positive values is sufficient — so the heuristic works here. But for SORT_STABLE (46% PTDR for heuristic), the heuristic generates groups but doesn't know to make ≥17 rows with equal primary keys — it generates 30 diverse rows, most of which don't trigger numpy's introsort switch. CDAIS doesn't rely on heuristic rules: it *proves* the minimum structure needed and generates exactly that. The advantage of CDAIS is not magnitude of detection but *guarantee* + *interpretability*: 1 trial, 6 rows, formal certificate. The heuristic needs 50 trials and cannot issue a certificate.

---

**Q139. Votre Table 4 (MIS results) — expliquez pourquoi SORT_KEY_SORTED a 8.3% oracle pass rate. Ce n'est pas une erreur dans votre oracle ?**

SORT_KEY_SORTED asserts: for all BY-cols in a PROC SORT result, the output is sorted on those columns. This sounds obviously true — PROC SORT sorts. The 8.3% oracle pass rate (1/12 applicable pairs) means the oracle violated this invariant 11 times out of 12. This is *not* an oracle error — it reveals something subtle about SAS PROC SORT semantics: when a PROC SORT uses `NODUP` or `NODUPKEY`, the output retains only distinct rows, and the sort key may not be globally monotone across all retained rows if the original sort key was a subset of the full composite key. Additionally, SAS PROC SORT with a `BY x y` clause sorts on x then y, but if x has ties, the secondary key y determines order — and the oracle's output for multi-key sorts wasn't always strictly monotone on x alone. The invariant was over-specified. Rejected correctly.

---

**Q140. LAG_NULL_FIRST_ROW: 0% oracle pass rate. Expliquez ce qui s'est passé.**

LAG_NULL_FIRST_ROW asserts: in any SAS LAG() translation, the first row of each BY-group should produce NULL (because LAG has no previous value at the group boundary). The oracle violated this on both applicable pairs (0/2 = 0%). Investigation revealed: the Python oracle for LAG used `df.shift(1)` which propagates the last row of the *previous group* as the "lagged value" for the first row of the *next group* — not NULL. This is actually the correct SAS behavior for LAG without BY-group reset: SAS LAG() maintains a queue across the entire dataset, not per group. The invariant was based on an incorrect mental model of SAS LAG semantics. Rejected. The discovery strengthened the paper: the LAG oracle was corrected based on this finding, and the corrected oracle is now used in the SemanticValidator. MIS acted as a *self-correction mechanism* for oracle errors.

---

**Q141. Vos 12 "cross-provider" pairs — c'est quoi le process exactement ? "Cross-provider" signifie quoi ?**

Two independent LLMs (minimax-m2.7:cloud via Ollama and nemotron-3-super:cloud via Ollama) each translated the same 12 SAS files independently, without seeing each other's output. "Cross-provider" means different model family, different training, different provider infrastructure — maximizing translation independence. For each of the 12 files: if both translations agree (cosine similarity of their Python outputs on adversarial inputs > threshold AND Groq LLaMA equivalence confidence ≥ 0.65), the pair is included in VTP as a cross-validated translation. If they disagree, manual review decides. The premise: two independently trained LLMs that both produce the same Python output for a given SAS snippet are more likely to be correct than either alone. This is the ensemble-validity argument for ground truth construction.

---

### D — The Six Error Classes in Detail

---

**Q142. Pour chaque classe d'erreur, donnez le trigger SAS exact et la mistranslation typique en une ligne.**

- **C1 RETAIN_RESET**: `RETAIN x 0; IF FIRST.grp THEN x=0; x+val;` → `df['x'] = df['val'].cumsum()` (missing groupby reset)
- **C2 LAG_QUEUE**: `lag_val = LAG(x);` → `df['lag_val'] = df['x'].shift(1)` (no BY-group boundary reset, and shift propagates cross-group)
- **C3 SORT_STABLE**: `PROC SORT DATA=ds; BY key; RUN;` → `df.sort_values('key')` (default quicksort, unstable; needs `kind='mergesort'`)
- **C4 NULL_ARITHMETIC**: `z = SUM(x, 5);` → `df['z'] = df['x'] + 5` (SUM skips missing values, x+5 propagates NaN)
- **C5 JOIN_TYPE**: `DATA out; MERGE left right; BY key; RUN;` → `pd.merge(left, right, on='key', how='inner')` (SAS MERGE without IN= is an outer join; inner is wrong)
- **C6 GROUP_BOUNDARY**: `IF FIRST.x THEN output;` → `df.head(1)` (selects one row from whole DF instead of first row per group)

---

**Q143. Pourquoi C4 (NULL_ARITHMETIC) s'appelle "NULL_Arithmetic" si le vrai bug c'est SUM() et pas l'arithmétique ?**

The name captures the class at the right level of abstraction. The bug category is "how null/missing values interact with arithmetic-like operations." In SAS, the `SUM()` function silently skips missing values — this is the "null-tolerant arithmetic" semantics. In Python, `x + 5` propagates NaN — standard IEEE 754 arithmetic. The class is called NULL_ARITHMETIC because the root cause is the divergent null-handling semantics between SAS's accumulated arithmetic model and Python's propagating NaN model. The specific trigger is `SUM()`, but the class name correctly identifies the semantic category. Alternative name considered: SUM_FUNCTION_SEMANTICS — but NULL_ARITHMETIC generalizes better if the taxonomy is extended to other null-related divergences (e.g., `MEAN()` with missing vs `np.mean()` with NaN).

---

**Q144. Pourquoi vous n'avez pas de classe pour les TYPE COERCIONS ? Par exemple SAS traite "123" comme numérique.**

Good catch — type coercion is a real SAS-Python divergence. SAS coerces character variables to numeric in arithmetic contexts (with a warning); pandas raises a TypeError. We excluded it from the six formalized classes for two reasons: (1) it's detectable syntactically — a static analyzer can flag `character_var + numeric_literal` in SAS without executing anything; (2) the Z3 encoding would require theory of strings, which is outside QF-LIA and significantly harder to reason about (string theory in SMT is PSPACE). The six classes were specifically chosen for their Z3-encodability in linear arithmetic. Type coercion is the highest-priority candidate for class C7 in the taxonomy extension.

---

**Q145. Pour C5 (JOIN_TYPE), votre witness utilise 3 rows dans la left table et 3 dans la right. Pourquoi pas 2+2 ?**

The JOIN_TYPE divergence requires: at least one key that exists only in the left table (left-only row) AND at least one key that exists only in the right table (right-only row). With 2+2, the minimum configuration would be: left = {1, 2}, right = {2, 3} — 1 shared key, 1 left-only, 1 right-only. This gives 3 outer join rows vs 1 inner join row — sufficient. The actual witness uses 3+3 because Z3's minimality objective over integer sum pushes key values to 1, 2, 3 (smallest positive integers), which naturally produces a 3+3 configuration: left = {1, 2, 3}, right = {2, 3, 4}. The minimality objective minimizes the *sum of all integer values*, not the *number of rows* — so the row count is a side effect of value minimization. For JOIN_TYPE, 2+2 vs 3+3 doesn't matter for detection; what matters is the non-overlapping key structure.

---

### E — What the Paper Doesn't Say (Professors Will Ask)

---

**Q146. Votre paper ne mesure pas la "false positive rate" de CDAIS — pourquoi ? Peut-il signaler un bug qui n'en est pas un ?**

CDAIS has no false positives by construction. If CDAIS reports a failure (oracle ≠ translation on witness W), there is a genuine behavioral divergence between the oracle and the translation on the synthesized input — this is a real semantic difference, not a false alarm. The issue is *false negatives* (bugs CDAIS misses), not false positives. CDAIS will not detect bugs from error classes outside the six formalized, and the certificate is only valid for the witness's structural shape. A translation that passes all six CDAIS checks could still have bugs — just not C1-C6 bugs on that shape. False positive rate = 0 by construction; false negative rate is bounded by coverage scope. The paper focuses on false negatives (what CDAIS misses) in the Limitations section.

---

**Q147. CDAIS et MIS se chevauchent-ils ? Peuvent-ils détecter le même bug ?**

They are designed to be complementary with minimal overlap. CDAIS targets known, formalized error classes (C1-C6) with specific witnesses and guarantees. MIS catches violations of confirmed invariants without knowing the error class. Consider RETAIN_RESET: CDAIS catches it via witness C1; MIS catches it via RETAIN_MONOTONE_CUMSUM invariant violation (confirmed). These two would both flag the same bug from different angles — providing corroborating evidence. But MIS can also catch bugs CDAIS doesn't formalize: if a translation breaks OUTPUT_NONEMPTY (outputs empty DataFrame when input is non-empty), CDAIS has no class for that, but MIS confirms it as an invariant. Conversely, CDAIS catches SORT_STABLE bugs; MIS's SORT_KEY_SORTED invariant was *rejected* — so MIS provides no signal for C3. The interaction is by design: complementary coverage, some overlap on the best-documented classes.

---

**Q148. Votre paper ne rapporte pas le recall de MIS — combien de vrai bugs une violation d'invariant détecte-t-elle réellement ?**

You're right — we report precision (confirmed invariants are correct properties of SAS semantics) but not recall (what fraction of all possible migration bugs would be caught by at least one confirmed invariant). Computing recall would require a labeled set of known bugs and testing whether each confirmed invariant catches it. We have the CDAIS witness bugs — of the 6 error classes, RETAIN_RESET is caught by RETAIN_MONOTONE_CUMSUM, JOIN_TYPE is caught by MERGE_OUTER_ROWCOUNT and NO_DUPLICATE_GROUP_KEYS, GROUP_BOUNDARY is partially caught by FIRST_LAST_SUBSET. C2/C3/C4 are not covered by any confirmed invariant. Estimated recall on the six formalized classes: ~50% (3/6 classes covered). On unformalized bugs: unknown. MIS recall is a known gap — the paper implicitly acknowledges it by calling CDAIS and MIS "complementary" rather than redundant.

---

**Q149. Vous dites que MIS "rejects candidates incompatible with real SAS semantics" — mais les 8 rejetés, c'est parce que SAS n'a pas ces propriétés, ou parce que les bonnes traductions ne les ont pas ?**

For oracle_violations > 0: the SAS oracle itself violated the invariant → the invariant is not a real SAS property → rejected because SAS doesn't satisfy it. For the 8 rejected invariants: COLUMN_SUPERSET (96.6% oracle pass — SAS doesn't always preserve all input columns, e.g. KEEP/DROP statements reduce column set); ROW_PRESERVATION_NON_FILTER (92.9% — SAS MERGE can produce fewer rows than either input if NOMATCH is used); ROW_EQUALITY_SORT (58.3% — PROC SORT NODUPKEY removes duplicates, changing row count); ROW_REDUCTION_AGGREGATION (66.7% — not all GROUP BY operations reduce rows in SAS); SORT_KEY_SORTED (8.3% — as discussed, multi-key sort semantics); LAG_NULL_FIRST_ROW (0% — oracle error corrected). The 8 rejections are genuine SAS semantic findings, not oracle errors (with the LAG exception that was corrected). This is why MIS adds value: it surfaces properties that *seem* obvious but aren't universally true in SAS.

---

**Q150. Pourquoi vous n'avez pas mesuré le taux d'amélioration de traduction grâce à CDAIS (avant vs après repair) ?**

We report CDAIS detection rate (100% for all 6 classes) and the fact that failing classes "inject structured repair hints into the LLM repair prompt for one bonus attempt." What we don't report: what fraction of CDAIS-failed translations were successfully repaired by the bonus attempt. This is a genuine gap in the evaluation. The reason: measuring repair success requires running the full translation pipeline with and without CDAIS repair on a labeled set of buggy translations — a controlled experiment separate from the benchmark. In the benchmark run, CDAIS ran as part of the pipeline and all outputs were scored; we cannot retrospectively isolate "would this translation have been correct without CDAIS repair?" The repair success metric is identified as a needed measurement in future work.

---

### F — Explain It Simply (Professors Test Understanding by Asking for Simpler Explanations)

---

**Q151. Expliquez CDAIS à quelqu'un qui ne sait pas ce qu'est Z3 mais connaît les tests logiciels.**

Imagine you're testing a function and you want to find an input that breaks it. Normal testing: you guess random inputs and hope one works. CDAIS: you look at the function's code, write down mathematically *what must be true about the input* to make it fail, then ask a constraint solver to find the smallest input that satisfies those conditions. The solver returns a 6-row table — the absolute minimum data needed to expose the bug. You run the buggy code on this table: it fails. You run the correct code: it passes. You now have a written proof that this specific 6-row table will always expose this class of bug for any code that has it. That proof is the coverage certificate.

---

**Q152. Expliquez MIS à un data engineer qui ne connaît pas la recherche formelle.**

You have 142 Python translations of SAS programs that you know are correct — verified by a SAS expert. You also have 18 candidate rules like "the output should never be empty if the input isn't" or "after a GROUP BY aggregation, there should be fewer rows than the input." You run every rule against every correct translation. If a rule passes on all 142 correct translations, you confirm it: any future translation that breaks this rule is likely wrong. If a rule fails even once on a verified-correct translation, you reject it: the rule is too strict for real SAS semantics. 10 rules survived. Now you have a checklist: any new translation that breaks one of these 10 rules has a semantic bug — guaranteed, because every known-correct translation satisfies them.

---

**Q153. Expliquez la différence entre votre SemanticValidator (Layer 2) et votre ValidationAgent (sandbox) — les deux exécutent du code, non ?**

The ValidationAgent (sandbox) just runs the Python code and checks: does it execute without crashing? It returns True if `exec()` completes without exception. It has no idea if the output is correct — it only knows the code is syntactically executable.

The SemanticValidator (Layer 2 of SemantiCheck) does something harder: it runs both the SAS oracle function AND the Python translation on the same synthetic input, then compares their outputs DataFrame by DataFrame. It checks: did both produce the same number of rows? The same column values? The same sort order? This is oracle-based behavioral testing — it doesn't just check "did it run", it checks "did it produce the right answer." Two completely different checks on the same translated code.

---

**Q154. Expliquez "structural shape" avec un exemple non-informatique.**

A structural shape is like a mold for the test data. If I tell you "the bug only appears in tables with exactly 2 groups of 3 people each", that's the structural shape: 2 groups × 3 rows. The coverage certificate says: "I tested a table of exactly this mold and the code passed, so it's correct for any table that fits this same mold — 2 groups of 3 people, regardless of what those people's names or numbers are." It doesn't say anything about tables with 5 groups, or tables where groups have different sizes. The mold is the guarantee's boundary.

---

**Q155. Expliquez pourquoi "the code runs without error" est not enough, with a concrete number example.**

SAS RETAIN: three sales amounts per region (Region A: 10, 20, 30; Region B: 5, 10, 15). Running total resets per region in SAS: A = [10, 30, 60], B = [5, 15, 30]. Python buggy code `df['total'] = df['amount'].cumsum()`: A = [10, 30, 60], B = [65, 75, 90]. The buggy code runs without error. On region A alone, the numbers are *identical*. But region B is completely wrong. A test with only one region gives a green checkmark. A test with two regions shows the bug — but only if you check the *values*, not just whether the code ran. This is exactly why execution-based testing misses this class of bug, and why CDAIS synthesizes data with 2+ regions specifically.

---

### G — Paper Vocabulary & Claims Under Oath

---

**Q156. Votre abstract dit "formally minimal" — dans quel sens exact ? Minimal par rapport à quoi ?**

Minimal in integer sum of variable values. The Z3 `minimize(sum(int_vars))` objective finds the satisfying assignment with the smallest total value across all integer variables. For RETAIN_RESET with G=2 groups, R=3 rows: the 6 variables {v[0][0], v[0][1], v[0][2], v[1][0], v[1][1], v[1][2]} are minimized in sum. Z3 returns all values = 1 (sum = 6). This is minimal in the sense that no smaller integer values (≥ v_min = 1 by constraint) can trigger the divergence. "Formally minimal" means Z3 proves this is the minimum — not just that we found a small witness, but that no smaller one satisfying the constraints exists. Alternative meanings of "minimal" we deliberately exclude: minimal by row count (harder to optimize in Z3), minimal by column count (not relevant), minimal by execution time.

---

**Q157. Votre paper dit que CDAIS "does not achieve a higher detection rate than exhaustive random testing" — c'est un aveu de faiblesse ou une clarification ?**

It is a deliberate clarification of scope — not a weakness admission. Given infinite random trials, random testing achieves 100% detection for any bug that ever manifests. The claim is that CDAIS is superior in three dimensions that random testing cannot match regardless of trial count: (1) **efficiency** — 1 trial instead of hundreds; (2) **formal guarantee** — a coverage certificate is a mathematical statement, not a probability; (3) **interpretability** — a 6-row witness tells you *why* the code fails, a 1000-row random dataset that happens to expose a bug tells you *that* it fails. The sentence in the paper was written to preempt exactly this attack from reviewers: we say it first, before a reviewer can claim we "missed" it.

---

**Q158. "The insight driving both methods is the same: structure beats randomness." Développez ce que ça signifie.**

CDAIS uses formal structure (Z3 constraint systems encoding divergence conditions) to generate test inputs — instead of sampling randomly from an unbounded space and hoping to hit a bug. MIS uses corpus structure (paired oracle-validated translations) to discover what "correct" means — instead of hand-writing formal specifications or guessing invariants without data. In both cases, structure is the source of the guarantee: Z3's structure proves the witness triggers the divergence; the corpus structure proves the invariants are universally valid. Random testing and manual specification are structureless — they work but provide no formal guarantee and scale poorly. Both methods apply the same epistemological principle: encode what you know about the problem's structure, then let the formal system do the work.

---

**Q159. "Coverage certificate" vs "formal proof of correctness" — quel est exactement le rapport entre les deux ?**

A formal proof of correctness (Z3 UNSAT on the full equivalence formula) says: for *all* inputs in the encoded domain, oracle and translation agree. A coverage certificate says: for *all* inputs of structural shape D, the translation is free from class C. These are related but different: a formal proof is stronger (covers all inputs in the domain, not just a shape class), but requires encoding the full program semantics in Z3 — tractable for 30% of blocks, intractable for 70%. A coverage certificate is weaker (scoped to shape class), but achievable for all 6 error classes because it only needs to encode the *divergence condition* for that class, which is much simpler than full equivalence. The two are complementary layers: Z3 formal proof where tractable, coverage certificates for the remaining patterns.

---

**Q160. Dans votre conclusion, vous écrivez "None of this requires a SAS runtime." Pourquoi c'est important industriellement ?**

SAS 9.4 licenses cost approximately $8,000–$25,000 per user per year for analytics licenses, with enterprise site licenses reaching hundreds of thousands. A company migrating from SAS *specifically cannot afford* to keep SAS running during the migration — that defeats the economic purpose. Yet every competitor migration tool requires SAS execution for ground truth: they run both the SAS original and the translated Python and compare outputs. Codara's entire validation stack (Z3, CDAIS witnesses, MIS invariant checks, Python oracle functions) produces semantic correctness evidence with zero SAS license dependency. This is the direct commercial value: a Deloitte client who canceled their SAS license on January 1 can still validate their migration translations using Codara on January 2.

---

### H — If They Ask You to Defend a Specific Table

---

**Q161. Table 2 de votre paper (per-class results) — pourquoi les synthesis times varient autant (15ms à 296ms) ?**

The variance comes from the constraint complexity per class:
- **NULL_ARITHMETIC (15ms)**: the encoding is trivial — one variable must be missing (NULL), one arithmetic expression must differ from SUM(). Z3 finds SAT immediately on a 1-variable problem.
- **LAG_QUEUE (16ms)**: requires encoding the implicit queue across 2 groups, 3 rows — 6 variables, linear inequalities. Simple LP.
- **RETAIN_RESET (31ms)**: slightly more complex — the cumsum correctness formula requires summing across rows within groups, verifying group boundary reset. More arithmetic terms.
- **GROUP_BOUNDARY (32ms)**: requires encoding first-row selection per group vs first-row of the whole DataFrame — 2 groups, 3 rows.
- **JOIN_TYPE (47ms)**: two tables with different key sets — more variables (left keys + right keys + overlap structure). The outer join vs inner join divergence requires encoding key membership.
- **SORT_STABLE (296ms)**: 17 variables with strict ordering constraint ($s_0 < s_1 < \cdots < s_{16}$) and the Distinct constraint was replaced with explicit ordering — more Simplex iterations to find the globally minimal satisfying assignment.

---

**Q162. Table 5 (MIS results) — FREQ_PERCENT_SUM_100 a 2 applicable pairs et 100% confirmation. Est-ce fiable avec seulement 2 pairs ?**

No — 2 applicable pairs is the smallest sample size from which any confidence about universality can be drawn. The LOO-CV provides partial reassurance: when either pair is removed (leaving 1 pair), the invariant remains confirmed. But 1 pair cannot distinguish a truly universal property from a coincidence. The honest statement: FREQ_PERCENT_SUM_100 is tentatively confirmed — it is a very natural property of PROC FREQ output (percentages must sum to 100 ± 0.1) that is almost certainly universally true, but 2 pairs is insufficient empirical evidence. The corpus needs more PROC FREQ examples to strengthen this confirmation. We report it as confirmed under our algorithm's criterion (oracle_violations = 0 with app > 0), but flag low-applicability invariants as requiring more pairs in the Limitations section.

---

**Q163. Pourquoi votre baseline random testing utilise 200 trials et votre baseline heuristic utilise 50 ? Les chiffres sont inconsistants.**

The difference reflects the cost of each baseline. Random testing generates a DataFrame in microseconds — 200 trials costs ~5ms total per class. Heuristic testing enforces structural constraints (≥2 groups, specific value ranges) that require more careful generation — 50 trials costs ~20ms. We chose trial counts that make both baselines competitive: 200 random trials is enough to see the PTDR stabilize (running more would not change the ~75% average materially); 50 heuristic trials is sufficient to observe the advantage over random for most classes. SORT_STABLE is the exception — 46% PTDR at 50 heuristic trials vs 100% for CDAIS in 1 trial — making the CDAIS advantage undeniable. Ideally, both baselines should use the same trial count (e.g., 200) for clean comparison; this is a presentation choice we would standardize in a journal version.

---

### I — Questions About What You Would Change

---

**Q164. Si vous refaisiez l'expérience MIS avec 500 pairs au lieu de 142, qu'attendriez-vous comme changement ?**

Based on the trajectory from 12 to 142 pairs (3 demoted, 3 promoted): additional pairs would likely: (1) demote FREQ_PERCENT_SUM_100 and MEANS_AGGREGATION_MONOTONE from confirmed — they each have 2 applicable pairs, and more PROC FREQ/PROC MEANS examples might reveal edge cases where the oracle violates them; (2) promote GROUP_BOUNDARY_STRICT_SUBSET from "not applicable" to either confirmed or rejected — it currently has 0 applicable pairs, so more FIRST./LAST. examples would give it a chance to be evaluated; (3) stabilize the 8 high-applicability confirmed invariants (OUTPUT_NONEMPTY at 142 pairs, COLUMN_DTYPE_STABILITY at 142 pairs) — these are unlikely to flip with more data because they are very simple universal properties. The LOO-CV stability suggests the current confirmed set is at least locally stable — but "locally stable" at 142 pairs doesn't mean "globally stable" at 500.

---

**Q165. Votre paper est soumis à SCAM 2026. Quels reviewers' comments attendez-vous ?**

Based on the paper's known limitations, likely comments:

1. **"The VTP corpus is annotated by a single person — add inter-rater agreement."** Expected and prepared for: we acknowledge it in Section 6.1 and propose κ measurement as future work.

2. **"Single-run evaluation — report confidence intervals."** Expected: the temperature=0.1 argument and ±1-2pp empirical variance is the defense, but reviewers may still require multi-run.

3. **"The 50-query ablation for RAPTOR is underpowered."** Expected: we note this limitation in the paper.

4. **"SORT_STABLE minimality override — is the 17-row threshold numpy-version dependent?"** Good catch — we tested on numpy 1.26; numpy 2.x may have different thresholds. We state the exact environment in the reproducibility section.

5. **"Why not compare against Daikon directly on the SAS migration problem?"** Reasonable — Daikon would require running SAS or a SAS emulator for execution traces, which we explicitly can't do without a license. This is the architectural reason we chose MIS's oracle-based approach.

---

*Total: 165 questions. Part 4 covers every number, every definition, every table, every rejected invariant, and every claim in the research paper.*

---

## MASTER CHEAT SHEET — Numbers You Must Know by Heart

| Item | Value |
|------|-------|
| Translation success rate | **72.4%** (target 70% ✓) |
| Syntax-valid merged output | **96.8%** (target 95% ✓) |
| Boundary detection F1 | **79.3%** (target 90% ✗) |
| Hard-tier translation | **53.7%** (missed) |
| RAPTOR advantage MOD/HIGH | **+12pp** (target ≥10pp ✓) |
| RAPTOR Hit-Rate@5 (all) | **0.84** vs 0.71 flat |
| RAPTOR Hit-Rate@5 (HIGH) | **0.71** vs 0.52 flat (+36%) |
| Complexity ECE | **0.061** (target <0.08 ✓) |
| Streaming: 10K lines | **1.34s, 61 MB** (target <2s, <100MB ✓) |
| CDAIS: error classes | **6/6** detected in 1 trial |
| CDAIS: avg witness size | **7.8 rows** (range 6–17) |
| CDAIS: avg synthesis time | **~73ms** |
| CDAIS: SORT_STABLE rows | **17 rows** (numpy introsort threshold) |
| CDAIS: SORT_STABLE time | **296ms** |
| Random baseline PTDR | **~75%** (200 trials) |
| Heuristic baseline PTDR | **~91%** (50 trials) |
| MIS: candidates | **18 total** |
| MIS: confirmed | **10/18 (55.6%)** |
| MIS: rejected | **8/18** |
| MIS: VTP corpus size | **142 pairs** (12 cross-provider + 130 enterprise) |
| MIS: LOO-CV | **0 fragile invariants** (142/142 folds stable) |
| MIS: LOO-CV runtime | **12.1s** on CPU |
| MIS: total runtime | **937ms** on CPU |
| Z3: torture test proof rate | **3/10 (30%)** |
| Z3: mean latency | **4.6ms** |
| Z3: patterns covered | groupby, sort_nodupkey, bool_filter |
| SCS torture test | **0.552** average |
| LLM minimax latency | **16.7s**, 52 tok/s |
| LLM nemotron latency | **6.8s**, 41 tok/s |
| KB pairs | **330** verified |
| Embedding dimensions | **768-dim** (Nomic v1.5) |
| Test count | **452** (248 at paper submission) |
| Audit grade | **A-** |
| Sprint duration | **15 weeks** (Feb 9 – Jun 9 2026) |
