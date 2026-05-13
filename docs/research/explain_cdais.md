# Plain-English Guide to the CDAIS + MIS Paper

This document explains every part of the paper in simple language.
No math required. Read this first, then read the paper.

---

## What is the paper about, in one sentence?

When an AI translates old SAS code into Python, it often produces code that looks
correct and runs without errors but gives the wrong answer. This paper builds two
tools to catch those silent bugs automatically.

---

## The Two Tools at a Glance

**CDAIS** — Think of it as a smart trap. For each known type of bug, it builds the
smallest possible dataset that will make the bug visible. If a translation passes the
trap, you get a written guarantee that this specific bug is not in that translation.

**MIS** — Think of it as a filter, not a discovery engine. We start with 18 candidate
rules that we wrote by hand. MIS runs those rules against a collection of translations
known to be correct and keeps only the rules that hold for every single one. The corpus
decides which rules survive — it does not invent the rules.

```
CDAIS                                  MIS
──────────────────────────────         ─────────────────────────────────
"Does this translation have            "Does this translation satisfy ALL
 the RETAIN_RESET bug?"                 the rules that every correct one does?"

Known bug → Z3 constraint              Handcrafted candidates
  → minimal witness (6 rows)             → run on 12 verified pairs
  → run oracle vs translation            → keep rules with 0 violations
  → pass = certificate                   → confirmed rules = specification

Catches: C1–C6 (known bugs)            Catches: anything that breaks
                                        a universal corpus rule
```

---

## Abstract (page 1)

The abstract is the 10-sentence summary of the whole paper. Here is what each sentence
is really saying:

1. "LLMs are used to migrate legacy code" — companies use AI to convert old SAS code
   to Python automatically.
2. "A serious problem remains" — the AI-generated Python often looks fine but computes
   the wrong numbers.
3. "These bugs are invisible to execution-based validation" — running the code does not
   help because the code does not crash; it just gives a wrong result quietly.
4. "CDAIS uses Z3 to build the smallest test input" — CDAIS uses a math solver to
   design a tiny (3–6 row) dataset engineered to expose a specific bug.
5. "For five of the six error classes" — it works for 5 out of 6 bug types we studied.
6. "It issues a coverage certificate" — if the translation passes the tiny test, CDAIS
   writes a formal promise: this type of bug is not present.
7. "MIS evaluates 18 handcrafted candidate invariants" — MIS starts from a fixed list
   of 18 rules we wrote manually, then runs them against 12 confirmed correct translations.
8. "Confirming those that hold universally" — rules that hold for every single oracle
   output are confirmed; the rest are rejected. This is validation, not discovery.
9. Numbers: CDAIS provides deterministic 1-trial detection for 5/6 classes; random
   testing only hits ~75% per try; MIS confirms 10 out of 18 rules on the 12-pair
   corpus; Z3 formally proves 30% of translations correct.
10. "Multi-layered semantic validation" — Z3, CDAIS, and MIS together provide
    complementary coverage that no single method achieves alone.

---

## Section 1 — Introduction

The introduction no longer has subsections (§1.1, §1.2, etc.). The paper uses inline
bold headings instead: **Research question.**, **Our approach.**, **Contributions.**
This is the standard format for IEEE conference papers.

**The problem** — This part explains why existing testing methods fail.

The motivating example uses SAS RETAIN. In SAS, `retain total 0` means: keep the
value of `total` from one row to the next, but reset it to zero every time a new
group starts. A common AI translation just does `df['amount'].cumsum()` — which adds
up all rows globally with no group reset. On a dataset with only one group, the result
happens to be correct. On a dataset with multiple groups, it is wrong. If your test
data only has one group, you will never see the bug.

The three bullets explain why standard approaches miss this:
- Running the code in a sandbox only checks that it does not crash.
- Z3 formal verification works for simple patterns like filters and aggregations but
  cannot handle stateful patterns like RETAIN or LAG.
- Random data generation has no guarantee it will produce multiple groups.

**Research question** — can we build a tool that is both **guaranteed** to expose a
specific bug (not random) and **automatic** (no SAS runtime, no manual work)?
The word "confirm" is used deliberately — the paper confirms invariant candidates
from a handcrafted list, it does not discover rules from scratch.

**Our approach** — Two paragraphs, one for each tool.

CDAIS: for each known bug type, we write a mathematical formula that says "this
input will make the correct translation and the broken translation give different
answers." We give that formula to Z3 (a math solver), which finds the smallest
numbers that satisfy it. That gives us our test dataset.

MIS: we start with 18 candidate rules we wrote by hand. We take 12 translations
known to be correct, run the candidates against them, and keep only the rules that
hold for every single oracle output. Confirmed rules become the migration
specification. The key point: MIS validates candidates, it does not invent them.
The spec is empirically grounded, not formally proven for all inputs.

**Contributions** — Three things the paper claims as new:

1. CDAIS is the first system to use SMT (math solver) synthesis specifically to
   generate adversarial test data for LLM code migration bugs. Coverage certificates
   are scoped to structural shape (same groups × rows as the witness).
2. MIS is the first corpus-driven migration invariant **confirmation** framework —
   candidates are hand-specified, but their validation across the corpus is automatic
   and requires no SAS runtime or manual labeling.
3. The paper provides real measured numbers, not estimates (important because the
   first draft used invented numbers — all values were re-run and verified).

---

## Section 2 — Background

This section gives readers enough context to understand the rest of the paper.

### 2.1 SAS→Python Migration

Explains what SAS is (a 1970s analytics language) and why migrating it is hard. Five
specific SAS features have no clean Python equivalent:

- **RETAIN**: a variable that carries its value from row to row, resetting at group
  boundaries. pandas has no built-in equivalent; you need `groupby().cumsum()` with
  a manual reset condition.
- **LAG()**: gives you the previous row's value, but it resets to NULL at each new
  group. `shift(1)` in pandas does not reset.
- **PROC SORT**: always stable (equal keys keep their original order). pandas
  `sort_values()` is unstable by default.
- **MERGE without IN=**: in SAS this is a full outer join. pandas `pd.merge()`
  defaults to inner join.
- **Missing value arithmetic**: SAS `SUM(x, 5)` treats missing as zero and returns 5.
  Python `x + 5` returns NaN if x is NaN.

### 2.2 SMT Solving and Z3

Z3 is a tool that can answer math questions like: "Is there a set of integers that
make this formula true, and if so, what is the smallest one?" We use it to find the
smallest dataset that exposes a bug. The key extension we use is `z3.Optimize`, which
does not just find any satisfying values — it finds the ones that minimize a given
objective (the sum of all values), giving us the smallest possible witness.

### 2.3 Counterexample-Guided Methods

CEGAR is a classical technique where you use counterexamples to gradually improve an
approximation of a program. The paper mentions it because CDAIS looks similar (both
use formal counterexamples), but they are different: CEGAR refines a model of the
program; CDAIS uses a counterexample to test a translation, not to refine anything.

### 2.4 Dynamic Invariant Detection

Daikon is a tool that watches a program run many times and guesses rules about its
behavior (e.g., "x is always greater than 0 after line 5"). MIS does something
similar: it watches correct translations run and guesses rules. The main differences
are that MIS watches pairs of programs (SAS oracle + Python translation), operates
on tables (DataFrames), and only checks 18 hand-picked candidate rules rather than
generating candidates automatically.

---

## Section 3 — Problem Formulation

This section turns the intuitions from Section 1 into precise mathematical definitions.
You do not need to understand the math; here is what each definition means in plain
English.

**Definition 1 (Migration)**: a translation is correct if, for every possible input
dataset, it produces the same output as SAS would.

**Definition 2 (Semantic Error Class)**: a specific named category of bug, defined
by two things: a rule for recognizing which SAS code it could affect (e.g., "this
block uses RETAIN"), and a rule for recognizing the broken Python pattern (e.g., "this
uses cumsum without a reset").

**Definition 3 (Witness)**: a concrete small dataset that makes the correct
translation and the broken translation give different outputs. The witness is specific
to one error class and one size/shape of data.

**Definition 4 (Coverage Certificate)**: a formal promise. If a translation produces
the same output as the SAS oracle on the witness, it gets a certificate saying: "this
translation is free from this specific bug type, for datasets of this exact size and
shape."

**Definition 5 (Migration Invariant)**: a property that holds for every correct
translation in the corpus. Example: "the output always has at least as many rows as
the input." This is a migration invariant for non-filter SAS operations.

---

## Section 4 — CDAIS

This is the first main technical section. It explains how CDAIS builds witnesses.

### 4.1 Error Class Taxonomy

#### Table 1 (Taxonomy Table) — What it shows

Six named bug categories, each with its SAS trigger and the wrong Python pattern.

| What the table column means | Plain English |
|---|---|
| ID | A short code for the bug type (C1 to C6) |
| Name | The bug's name |
| SAS Trigger | What SAS construct causes this bug when poorly translated |
| Common Mistranslation | The specific wrong Python pattern the AI usually writes |

- **C1 RETAIN_RESET**: AI forgets to reset the running total at each group boundary.
- **C2 LAG_QUEUE**: AI uses `shift(1)` which does not reset at group starts.
- **C3 SORT_STABLE**: AI uses an unstable sort when SAS requires a stable one.
- **C4 NULL_ARITHMETIC**: AI uses `x + 5` when SAS `SUM(x, 5)` means "skip missing
  values." The addition propagates NaN; SUM does not.
- **C5 JOIN_TYPE**: AI uses inner join when SAS MERGE without IN= is an outer join.
- **C6 GROUP_BOUNDARY**: AI picks the first row of the whole table when SAS
  `FIRST.x` means the first row of each group.

**Important note on C4**: the bug is specifically in the SUM() function, not in
addition. `y = x + 5` behaves the same in both SAS and Python (both propagate
missing/NaN). The bug only appears when the SAS code uses `SUM(x, 5)`.

---

#### Concrete examples: C1 and C5 side by side

**C1 — RETAIN_RESET** (the most common and most dangerous bug)

```
SAS (correct behavior):            Correct Python translation:
─────────────────────              ──────────────────────────
data output;                       df = df.sort_values('region')
  set sales;                       df['total'] = (
  by region;                           df.groupby('region')['amount']
  retain total 0;                        .cumsum()
  if first.region then total=0;   )
  total + amount;
run;
                                   Broken Python (LLM often writes):
                                   ─────────────────────────────────
                                   df['total'] = df['amount'].cumsum()
                                   # ↑ no group reset!

On this data:        Correct result:    Broken result:
 region  amount      total              total
   A       10          10                10
   A       20          30                30
   B        5 ←reset    5 ✓             35 ✗  (should reset to 5)
   B       15          20 ✓             50 ✗
```

**C5 — JOIN_TYPE** (silent data loss)

```
SAS MERGE without IN= = OUTER JOIN    Broken Python (LLM default):
──────────────────────────────────    ────────────────────────────
data merged;                          result = pd.merge(left, right,
  merge left right;                       on='key')
  by key;                             # defaults to how='inner' !
run;

Left table:   Right table:   Correct outer join:   Broken inner join:
 key  val_L    key  val_R     key  val_L  val_R      key  val_L  val_R
  1     A        2     X       1     A    NaN          2     B      X
  2     B        3     Y       2     B     X    ✓      3     C      Y
  3     C        4     Z       3     C     Y    ✓
                              4    NaN     Z
                              ↑ key=1 and key=4 preserved   ↑ silently lost!
```

---

#### Figure 4 — Error Taxonomy Tree

This figure groups the 6 error classes by their root cause:
- C1, C2 are both accumulation bugs (variables that carry state across rows).
- C3 is an ordering bug (sort stability).
- C6 is a boundary bug (group vs. whole-table scope).
- C4 is a null/missing value bug.
- C5 is a set-join bug (which rows survive the merge).

The tree helps you see that the bugs are structurally different, which is why you
need six separate Z3 encodings rather than one general one.

### 4.2 Z3 Constraint Encoding

This section shows, for one bug (RETAIN_RESET), exactly how we translate the bug
description into a math formula that Z3 can solve.

The math says: define variables representing cell values in a 2-group, 3-row table.
Compute what the correct cumsum (per group) would be. Compute what the wrong cumsum
(global, ignoring groups) would be. Add a constraint that they must differ at some
row. Then ask Z3: "find the smallest numbers for which this is true."

Z3 finds that any positive integer works for all values (e.g., all 1s), and the
minimum is achieved at v=1 everywhere. That gives us the 6-row all-ones witness.

You do not need to understand the specific formulas. The key idea is: we describe the
bug in math, Z3 finds the smallest data that triggers it.

```
How Z3 builds the RETAIN_RESET witness:

Step 1 — Name the cells (symbolic variables):
         group A: v[0][0]  v[0][1]  v[0][2]
         group B: v[1][0]  v[1][1]  v[1][2]

Step 2 — Write what the CORRECT output looks like:
         correct[A] = cumsum within A = [v[0][0], v[0][0]+v[0][1], ...]
         correct[B] = cumsum within B = [v[1][0], v[1][0]+v[1][1], ...]
                                         ↑ resets at each new group

Step 3 — Write what the BROKEN output looks like:
         broken = global cumsum = [v[0][0], ..., v[0][2]+v[1][0], ...]
                                                  ↑ never resets

Step 4 — Add the constraint "they must differ at row 3":
         v[0][0] + v[0][1] + v[0][2]  ≠  v[1][0]
         (broken at row 3)               (correct at row 3)
         → this holds whenever v[0][0]+v[0][1]+v[0][2] > 0

Step 5 — Minimize: make all values as small as possible → Z3 picks v=1 everywhere

Result:
  group  value
    A      1      ← v[0][0]
    A      1      ← v[0][1]
    A      1      ← v[0][2]
    B      1      ← v[1][0]  ← boundary: correct resets, broken continues
    B      1
    B      1

  Correct output: [1, 2, 3,  1, 2, 3]   (resets at B)
  Broken output:  [1, 2, 3,  4, 5, 6]   (never resets)
  Bug visible at row 4:  1 ≠ 4  ✓
```

### 4.3 Minimum Witness Synthesis

#### Algorithm 1 — What it does, step by step

1. Create a Z3 optimizer (a solver that finds the smallest solution, not just any solution).
2. Set a timeout so it does not run forever.
3. Encode the bug's divergence condition into Z3 constraints.
4. Tell Z3 to minimize the sum of all integer variables (this gives the smallest values).
5. Ask Z3 to solve.
6. If it cannot solve (UNSAT or timeout), return empty — no witness exists.
7. If it solves, extract the model (the concrete values Z3 found).
8. Convert those values into a pandas DataFrame.
9. Return the DataFrame as the witness.

**Time**: this takes under 50ms in practice because the math involved (linear
arithmetic) is well-handled by Z3's algorithms.

**Why minimize?**: because we want the witness to be as small and readable as
possible. 6 rows of all-1s is much easier to understand than 1,000 random rows.

```
CDAIS witness (6 rows)       vs.     Random test data (1,000 rows)
──────────────────────               ─────────────────────────────
 group  value                         group  value
   A      1    ← engineered            C       847
   A      1      to expose             A        23
   A      1      the exact             B       412
   B      1    ← reset boundary        A         7
   B      1                            ...  (997 more rows)
   B      1

Developer reads it and immediately    Developer has no idea which rows
knows: "this tests per-group reset"   triggered the failure, or why
```

#### Figure 2 — CDAIS Synthesis Workflow

This figure shows the flow of Algorithm 1 visually:

1. Start with an error class (e.g., RETAIN_RESET).
2. Encode it into Z3 constraints (the divergence condition).
3. Run `z3.Optimize()` with minimize objective.
4. **Branch**: SAT → extract model → DataFrame. UNSAT → return empty.
5. Run the SAS oracle and the buggy translation on the DataFrame.
6. **Branch**: outputs differ → issue coverage certificate. Do not differ → certificate invalid (C3 case).

The C3 (SORT_STABLE) case always ends up in the "do not differ" branch because
Python's sort on 2 rows is deterministic regardless of the stability setting.

### 4.4 Coverage Certificates

#### Theorem 1 — What it says in plain English

"If a translation produces the same output as the SAS oracle on the witness, then
the bug is definitely not in that translation for datasets of the same size and shape."

**Why this is true**: the witness was specifically built so that any translation
that has the bug WILL produce a different output from the oracle. So if it does not
differ, the bug is absent. It is a logical guarantee, not a statistical one.

**Important limitation**: the guarantee only applies to datasets with the same
number of groups and rows as the witness. A 2-group × 3-row witness certifies
"no RETAIN_RESET bug on any 2-group × 3-row dataset." It says nothing about
20-group datasets. This is clearly stated and is a known design trade-off.

```
What a coverage certificate looks like (simplified):

  ┌────────────────────────────────────────────────────────┐
  │  CDAIS COVERAGE CERTIFICATE                            │
  ├────────────────────────────────────────────────────────┤
  │  Block:        block_id = a3f2b1c9                     │
  │  Error class:  RETAIN_RESET (C1)                       │
  │  Witness:      6-row DataFrame (2 groups × 3 rows)     │
  │  Test result:  PASS  — oracle output = actual output   │
  │                                                        │
  │  GUARANTEE:                                            │
  │  This translation is free from the RETAIN_RESET bug    │
  │  on any dataset with exactly 2 groups, 3 rows each.    │
  │                                                        │
  │  NOT covered:  other shapes, other error classes,      │
  │                datasets with more groups or rows.      │
  └────────────────────────────────────────────────────────┘

  Stored in: partition.metadata["cdais_certificates"]["C1"]
```

### 4.5 Integration in the Translation Pipeline

This section explains where CDAIS fits in the actual software system.

The pipeline order is:
1. Translate the SAS code using an LLM.
2. Run the translated Python in a sandbox to check it does not crash.
3. Run Z3 formal verification on simple patterns.
4. Run CDAIS: synthesize witnesses for all applicable error classes, run them.
5. Classes that pass get a certificate. Classes that fail get repair hints sent back
   to the LLM for one more repair attempt.

---

## Section 5 — MIS

MIS takes the opposite approach from CDAIS. Instead of targeting known bugs, it
learns from correct translations what "correct" looks like.

### 5.1 Intuition

CDAIS asks: "does this translation have bug X?" MIS asks: "does this translation
satisfy the candidate rules that every correct translation we have seen also satisfies?"

The key distinction: MIS does not ask "what rules exist?" — the analyst writes those.
MIS asks "which of our candidate rules survive the corpus?" The corpus decides; the
analyst proposes. Think of it as invariant **validation**, not invariant discovery.

```
18 handcrafted candidate rules
         │
         ▼
┌─────────────────────────────────────────────┐
│  Run each rule on 12 verified (SAS, Python) │
│  pairs using adversarial input data         │
└─────────────────────────────────────────────┘
         │
    For each rule:
         │
         ├── Not applicable (pattern absent from corpus)? → SKIP (4 rules)
         │
         ├── oracle_violations > 0? (rule fails on correct SAS output)
         │       └──→ REJECT — rule is too strict (8 rules)
         │
         └── oracle_violations = 0? (holds for every oracle output)
                 └──→ CONFIRM — rule is a real SAS property (10 rules)

Confirmed rules become the migration specification.
A new translation that violates a confirmed rule is flagged for repair.
```

**Concrete example — ROW_PRESERVATION_NON_FILTER:**

```
Rule: "for non-filter operations, output must have ≥ as many rows as input"

Applied to 12 pairs (all 12 applicable):

  Pair 1: SAS data step (no filter) → input=50 rows, oracle output=50 rows ✓
  Pair 2: PROC MEANS (aggregation)  → input=100 rows, oracle output=5 rows
          ← WAIT — this is an aggregation, rule says "non-filter" so SKIP
  Pair 3: RETAIN accumulator        → input=30 rows, oracle output=30 rows ✓
  ...all 12 applicable pairs: oracle output ≥ input rows

oracle_violations = 0  →  CONFIRMED ✓

Now test a new translation:
  input=200 rows, actual output=180 rows  →  VIOLATION FLAGGED
  "this translation is losing 20 rows for a non-filter operation"
```

### 5.2 Invariant Candidate Library

We defined 18 candidate rules manually. They fall into four groups:

- **Structural** (7 rules): about the shape of the output. Example: "the output
  has at least as many rows as the input" (for non-filter operations).
- **Relational** (6 rules): about relationships between values. Example: "the
  cumulative sum is always non-decreasing" (for RETAIN).
- **Ordering** (1 rule): "the output is sorted by the sort key."
- **Semantic** (4 rules): about specific semantic behaviors. Example: "the first
  row of each group has a NULL lag value."

### 5.3 Algorithm 2 — What it does, step by step

**Phase 1 — Collect observations:**
For each of the 12 correct (SAS, Python) pairs:
1. Generate adversarial input data (specifically designed to stress-test the code).
2. Run the SAS oracle on it (get the "correct" output).
3. Run the Python translation on it (get the "actual" output).
4. Store all three: input, oracle output, actual output.

**Phase 2 — Confirm invariants:**
For each of the 18 candidate rules:
1. Find which pairs the rule is applicable to (based on whether the SAS pattern matches).
2. Count how many times the rule fails on the oracle outputs (oracle_violations).
3. If the rule never fails on the oracle (oracle_violations = 0), confirm it.
4. Count how many times the rule fails on the actual translations (actual_violations).
   This tells us which patterns are hardest to migrate correctly.

**Phase 3 — Output:**
Return the confirmed rules (10), the rejected ones (8), and statistics.

**Why "oracle_violations = 0" is the threshold**: if a rule fails even once on a
correct SAS oracle output, it means the rule is too strict — it describes something
that SAS itself does not always do. We cannot use it as a requirement for Python
translations.

### 5.4 The Difference Between Oracle Violations and Actual Violations

- `oracle_violations = 0`: the rule is a real property of correct SAS behavior.
- `actual_violations > 0`: some correct Python translations break the rule. This is
  useful information — it tells us which SAS patterns are hardest to translate.

### 5.5 Applying Confirmed Invariants

Once we have confirmed rules, we can test a new translation:
1. Generate adversarial input.
2. Run the oracle to get the expected output.
3. Check each confirmed rule that applies to this SAS pattern.
4. Report any broken rules as semantic error signals.

---

## Section 6 — Combined System

#### Figure 1 — Five-Layer Validation Pipeline

This figure shows all five validation steps in order, from top to bottom:

| Layer | Tool | What it catches |
|---|---|---|
| 1 | ValidationAgent (exec sandbox) | crashes, syntax errors, missing output |
| 2 | Z3 Verification Agent | formally proves simple patterns correct (30% of blocks) |
| 3 | Semantic Validator (oracle diff) | wrong answers on pattern-specific inputs |
| 4 | CDAIS Runner | known bug classes (C1–C6), issues certificates |
| 5 | MIS Invariant Check | violations of corpus-derived universal rules |

```
  SAS code (input)
        │
        ▼
  ┌─────────────────────────┐
  │  LLM Translation        │──→ Python code (draft)
  └─────────────────────────┘
        │
        ▼
  ┌─────────────────────────┐  catches: crashes, import errors,
  │  Layer 1: Exec Sandbox  │           code that does not run
  └─────────────────────────┘
        │ PASS
        ▼
  ┌─────────────────────────┐  catches: groupby/sort/filter patterns
  │  Layer 2: Z3 Formal     │           formally provable (3/10 blocks)
  └─────────────────────────┘  ← free if pattern is in Z3's fragment
        │ PASS
        ▼
  ┌─────────────────────────┐  catches: wrong answers when running
  │  Layer 3: Semantic      │           oracle vs. translation on
  │          Validator      │           pattern-specific inputs
  └─────────────────────────┘
        │ PASS
        ▼
  ┌─────────────────────────┐  catches: C1–C6 known bug classes
  │  Layer 4: CDAIS         │  issues: coverage certificates
  └─────────────────────────┘  on fail: sends repair hint to LLM
        │ PASS
        ▼
  ┌─────────────────────────┐  catches: violations of confirmed
  │  Layer 5: MIS           │           corpus invariants
  └─────────────────────────┘  on fail: sends repair hint to LLM
        │ PASS
        ▼
  Translation accepted
  Certificates stored in partition.metadata
```

Each layer catches different things. If a translation passes all five layers, you
have much stronger confidence than if it only passed a syntax check.

**SemanticValidator** (Layer 3): this is the layer between Z3 and CDAIS. Unlike
the sandbox (which only checks "did it run?"), the SemanticValidator checks "did it
produce the right answer?" It runs the SAS oracle and the Python translation on
the same adversarial inputs and compares the outputs directly.

**Interaction between CDAIS and MIS**:
- CDAIS runs first. If it finds a bug, the system tries to repair the translation
  once more, then continues.
- MIS runs after CDAIS. Broken invariants are added to the repair hints.
- Both systems store their results in the translation metadata for later inspection.

---

## Section 7 — Experimental Evaluation

### 7.1 Datasets

#### Table (Dataset Roles) — What it shows

Three datasets, each used for a different purpose. The paper now explicitly states
what each dataset **cannot** conclude as well as what it validates.

| Dataset | What it is | Validates | Cannot Conclude |
|---|---|---|---|
| TC (Taxonomy Corpus) | 330 SAS→Python pairs from the knowledge base | Error frequency — how often each bug type appears (§4.1) | Behavioral correctness; the verifier only checks imports and output type, not runtime behavior |
| GSC (Gold Standard SAS Corpus) | 61 SAS files with hand-written annotations | CDAIS witness testing, Z3 evaluation | MIS invariants — the `.gold.json` files contain no Python translations |
| VTP (Verified Translation Pairs) | 12 (SAS, Python) pairs verified by two LLMs + manual review | MIS invariant confirmation | Generalization beyond 12 pairs — a larger corpus might reject some confirmed rules |

**Why three separate datasets?** Each serves a different validation purpose and has
different properties. TC has many pairs but the translations may have subtle bugs.
GSC has expert annotations but no Python code. VTP has verified correct translations
but only 12 of them. Using the wrong dataset for the wrong purpose would give
misleading results.

**Why only 12 VTP pairs?** The VTP filter requires: (1) both LLMs produced a
translation, (2) a third LLM (Groq LLaMA) confirmed they are equivalent, and (3)
manual review agreed. Only 12 pairs in the benchmark JSONs passed all three checks.

### 7.2 Metrics

Five measurements used in this paper:

- **GDR** (Guaranteed Detection Rate): how many of the 6 bug classes does CDAIS
  catch in exactly 1 trial? Answer: 5/6 = 83.3%.
- **PTDR** (Per-Trial Detection Rate): if you run random/heuristic testing once,
  what is the chance it exposes the bug? Varies by class, average ~75%.
- **Synthesis Time**: how long does Z3 take to build the witness? Average ~50ms.
- **MIS Confirmation Rate**: how many of the 18 candidate rules survived? 10/18 = 55.6%.
- **Z3 Formal Proof Rate**: what fraction of translations did Z3 formally prove
  correct? 3/10 = 30%.

### 7.3 CDAIS Effectiveness

#### Table 1 (CDAIS Summary) — What it shows

Three rows: random testing, heuristic testing, and CDAIS. Compared across four
dimensions: how many classes detected, per-trial success rate, data size, and time.

The key point: random testing detects all 6 classes eventually, but needs up to 200
tries and succeeds only 74% per try. CDAIS detects 5/6 with a 100% guarantee in
1 try. The one miss (SORT_STABLE) is a known limitation explained separately.

```
Why 1 guaranteed trial beats 74% × many trials (for RETAIN_RESET):

  Random testing (200 trials):
  Trial  1: no multiple groups generated → MISS
  Trial  2: multiple groups, but totals happen to match → MISS
  Trial  3: BUG FOUND ✓
  Trial  4: no multiple groups → MISS
  ...
  After 200 trials: ~68% of individual trials caught it.
  You need to aggregate many trials to be confident.

  CDAIS (1 trial):
  Witness: exactly 2 groups, 3 rows each, all values = 1
  Oracle:  [1,2,3, 1,2,3]
  Actual:  [1,2,3, 4,5,6]   ← guaranteed to differ at row 4
  → BUG FOUND ✓  in 1 try, every time, no luck involved
```

#### Table 2 (Per-Class Results) — Detection rates visualised

```
Error Class       Random PTDR    Heuristic PTDR   CDAIS
                  (1 of 200)     (1 of 50)        (1 trial)
──────────────────────────────────────────────────────────
RETAIN_RESET      ████░░  68%    ██████████ 100%   100% ✓
LAG_QUEUE         ████░░  68%    ██████████ 100%   100% ✓
SORT_STABLE       ██░░░░  29%    ███░░░░░░░  44%   N/A  ✗
NULL_ARITHMETIC   ██████ 100%    ██████████ 100%   100% ✓
JOIN_TYPE         ██████ 100%    ██████████ 100%   100% ✓
GROUP_BOUNDARY    █████░  82%    ██████████ 100%   100% ✓

CDAIS advantage: not a higher detection rate — a GUARANTEE in 1 trial
```

#### Table 2 (Per-Class Results) — What it shows

One row per error class. Columns:
- **CDAIS Detects?**: yes for 5 classes, no for SORT_STABLE.
- **Random PTDR**: the chance a single random test (out of 200) catches this bug.
  Very low for RETAIN_RESET (68.5%) and SORT_STABLE (29%). High for NULL_ARITHMETIC
  and JOIN_TYPE (100%).
- **Heuristic PTDR**: the chance a heuristic test (forces ≥2 groups) catches it.
  Higher than random for all classes except SORT_STABLE.
- **Witness Rows**: how many rows the Z3 witness contains. All 6-row (2 groups × 3
  rows) except SORT_STABLE which only needs 2 rows.
- **Synthesis (ms)**: how long Z3 took. NULL_ARITHMETIC is 0ms (trivially SAT),
  RETAIN_RESET is 187ms (largest constraint system). Average 50ms.

#### Figure 3 — Per-Class Detection Rate Comparison

A horizontal bar chart with 3 bars per error class (blue = random, green = heuristic,
amber = CDAIS). The chart makes it visually clear that:
- For RETAIN_RESET and LAG_QUEUE, random testing only reaches ~68% per trial while
  CDAIS guarantees 100%.
- For SORT_STABLE, CDAIS shows a hatched "N/A" bar because the certificate is invalid.
- For NULL_ARITHMETIC and JOIN_TYPE, all three methods reach 100% (these bugs are easy
  to detect even randomly because they affect every test input).

#### 7.3.1 SORT_STABLE limitation

The SORT_STABLE bug depends on the sort algorithm being non-deterministic on equal
keys. But the Z3 minimality objective forces us to use only 2 rows. On 2 equal-key
rows, Python's Timsort always preserves order — it happens to be deterministic there.
So the witness never actually triggers the instability.

The certificate is therefore meaningless for C3: it says "passed" but the test was
not actually stressful enough to expose the bug. The fix would be to force a 4-row
witness for C3 specifically. This is left as future work.

### 7.4 MIS Results

#### Table 3 (MIS Invariants) — What it shows

18 rows, one per candidate invariant. Columns:
- **Category**: structural / relational / ordering / semantic.
- **Applicable Pairs**: how many of the 12 VTP pairs this rule applies to (based on
  whether the SAS code uses the relevant pattern).
- **Oracle Pass Rate**: out of applicable pairs, what fraction of oracle outputs
  satisfy the rule. Must be 100% to confirm.
- **Confirmed**: Yes if oracle pass rate = 100% and applicable pairs > 0.

**10 confirmed invariants** — all of them are about high-level structural properties
(output is non-empty, columns are preserved, row count is preserved for non-filters,
dtypes are stable, etc.). These are the "obvious" rules that all correct translations
naturally obey.

**4 rejected because too aggressive**:
- SUM_PRESERVATION: fails when RETAIN adds computed rows (output has more rows than input).
- ROW_REDUCTION_AGGREGATION: too strict about row counts after aggregation.
- LAG_NULL_FIRST_ROW: our oracle's LAG implementation has a different assumption
  about what "first row of group" means in edge cases.
- SORT_KEY_SORTED: some PROC SORT outputs are sorted by multiple keys, not a single
  monotone key.

**4 not applicable**: these target FIRST./LAST., FREQ, dedup, and group-boundary
patterns that do not appear in the 12-pair VTP corpus. They would likely be confirmed
on a larger corpus.

```
How an invariant catches a bug in a NEW translation:

  New pair received: RETAIN-based accumulator

  Step 1 — Generate adversarial input (3 groups, values include NaN):
    group  amount
      A      10
      A      20
      B       5
      B      15
      C       8

  Step 2 — Run applicable confirmed invariants:

    RETAIN_MONOTONE_CUMSUM: within each group, cumsum must be non-decreasing
      Oracle output: [10,30,  5,20,  8] ✓ (non-decreasing within each group)
      Actual output: [10,30, 35,50, 58] ✗ ← global cumsum, never resets

    ROW_PRESERVATION_NON_FILTER: output row count ≥ input row count
      Oracle: 5 rows in → 5 rows out ✓
      Actual: 5 rows in → 5 rows out ✓ (doesn't catch this bug)

  Step 3 — RETAIN_MONOTONE_CUMSUM flags the violation → repair hint sent to LLM
```

### 7.5 Z3 Formal Verification

#### Table 4 (Z3 Results) — What it shows

Z3 was run on 10 code blocks from a "torture test" file. It could formally prove
3 of them correct. The other 7 are outside what Z3 can express.

- **What Z3 proved**: simple aggregation (groupby), sort with deduplication, and
  boolean filtering. These are expressible in linear arithmetic, which Z3 handles well.
- **What Z3 could not prove**: RETAIN (stateful), hash objects, macros, TRANSPOSE.
  These involve loops, state, or complex data transformations that Z3 cannot express.
- **4.6ms average**: very fast. Z3 is almost free if the translation is simple enough.

### 7.6 Translation Quality Baseline

#### Table 5 (LLM Benchmark) — What it shows

Two AI models were tested on the same 10 hard SAS blocks:
- Both scored 10/10 on syntax (the code ran without errors).
- Both showed 3/10 Z3 formally proved — verified independently for each model from
  the benchmark run output (`z3_status=formal_proof` on blocks 5, 6, 10 for both).
- The average semantic correctness score was 0.552 (about 55%).

This is the core problem statement quantified: the AI gets 100% on "does it run?"
but only 55% on "does it produce the right answer?"

The Tok/s column (52 for minimax, 41 for nemotron) is computed as the average tokens
per second across all 10 blocks from the benchmark run — verified from the benchmark
output file.

### 7.7 Ablation: Does the Minimality Matter?

#### Table 6 (Ablation) — What it shows

Three rows: random data, heuristic data, and CDAIS witness data. Compared on:
number of rows, per-trial detection rate, how many trials you need to guarantee
detection, and whether a human can read and understand the test data.

The point: CDAIS is not just faster. A 6-row witness with values of 1 tells a
developer exactly what property is being tested. A 1,000-row random dataset that
happens to expose a bug gives you no information about why it failed.

### 7.8 Reproducibility

#### Table (Script Mapping) — What it shows

Every result in the paper maps to a specific script that any reader can run to
reproduce it. No external API keys needed for CDAIS, MIS, or Z3 tests.

- Tables 1 and 2 → `eval_cdais_direct.py`
- Table 3 (MIS) → `run_mis.py`
- Table 4 (Z3) → `z3_audit.py`
- Tables 5 and 6 → `model_benchmark.py`

LLM benchmark (Table 5) requires a running Ollama server with the models downloaded,
but all other evaluations are fully deterministic and self-contained.

---

## Section 8 — Limitations and Threats to Validity

This section is about honesty. It states clearly what the system cannot do.

### 8.1 Explicit Limitations

**CDAIS guarantees:**
- "This specific bug type is absent from this translation, for datasets with exactly
  this many groups and rows."

**CDAIS does NOT guarantee:**
- Correctness on datasets of different sizes.
- Absence of bugs not in the 6-class taxonomy.
- Correctness for SORT_STABLE (the witness is too small).
- Equivalence for complex SAS patterns like macros or hash objects.

**MIS can:**
- Confirm rules that hold universally across all oracle-validated pairs in the corpus.
- Correctly reject rules that are too aggressive for real SAS semantics (8 of 18).

**MIS cannot:**
- Check rules about SAS patterns not present in the 12-pair corpus (4 candidates
  were simply inapplicable — not enough to confirm or reject them).
- Know whether a confirmed rule generalizes beyond 12 pairs. The 100% pass rate
  means "held on every pair we could verify" — not "will always hold." A larger
  corpus might reject some currently confirmed rules.
- Invent new rules — the 18 candidates are fixed and handwritten by the analyst.
  MIS is a filter, not a generator.
- Prove anything formally — confirmed rules are empirically universal on the observed
  corpus, not mathematically proven for all inputs.

**MIS corpus size — explicit warning:** 12 pairs is a known bottleneck. The 100%
confirmation rate is necessary but not sufficient for universality. Before using
these confirmed rules prescriptively (e.g., as hard constraints on future translations),
the corpus should be expanded to 50+ pairs. This is stated as future work in the paper.

**Out of scope entirely:**
- Full correctness proofs (mathematically undecidable).
- SAS macros with dynamic code generation.
- Performance or memory properties.

### 8.2 Threats to Validity

Four standard threats and how we addressed each:

- **Internal validity** (are results accurate?): gold pairs were manually curated and
  verified by running both sides. Mitigation: cross-checked against expected outputs.
- **External validity** (does this generalize?): only SAS→Python was tested. The
  approach could generalize to COBOL→Java or SAS→PySpark but was not tested there.
- **Construct validity** (does the metric measure the right thing?): tests use
  synthetic adversarial data, not real production SAS inputs. Mitigation: the
  adversarial generator specifically targets known failure modes.
- **Oracle correctness** (is the oracle right?): oracle functions are verified by
  337 unit tests and cross-checked against the SAS 9.4 Language Reference. The
  rejected LAG_NULL_FIRST_ROW invariant (0% pass rate) actually revealed a real
  discrepancy in our oracle — we reported this honestly rather than hiding it.

---

## Section 9 — Related Work

Five families of prior work, each contrasted with what the paper does:

| Prior work | What it does | How CDAIS/MIS differs |
|---|---|---|
| TransCoder, Avatar | LLMs translating code between languages | No correctness guarantees at all |
| **Pan et al. (ICSE 2024)** | Empirical study of bugs introduced by LLMs during code translation — finds semantic errors are the most frequent and hardest to detect | Directly motivates CDAIS and MIS; cited in the Introduction |
| Sketch, Korat | Generate test inputs from formal specs | Require manual specs; CDAIS uses empirical taxonomy |
| Daikon | Discover program invariants from execution traces | Single program, general variables; MIS uses paired corpus, DataFrames |
| CEGAR | Counterexamples to refine abstractions | Refines models; CDAIS uses witnesses to test, not to refine |
| Viya, SAS2Python | Commercial migration tools | Pattern-matching only; no formal guarantees |

---

## Section 10 — Conclusion

Three paragraphs, each making one point:

1. **What was built and measured**: CDAIS provides deterministic 1-trial detection for
   5/6 bug classes using 3–6 row witnesses synthesized in ~50ms, with coverage
   certificates scoped to structural shape. MIS confirmed 10/18 candidate invariants
   from 12 pairs (correctly rejecting 8 over-aggressive ones). Z3 proves 30% of
   translations formally in 4.6ms. Together: multi-layered semantic validation, not
   a single blanket guarantee.

2. **The key insight**: "structure beats randomness." A formal constraint finds the
   exact divergence point; corpus-validated rules find what "correct" means from data.
   Neither requires a SAS runtime, formal specs, or human annotations beyond the
   hand-specified invariant candidates.

3. **Future work**: grow the taxonomy from 6 to 20+ classes; apply to other migration
   paths; use confirmed invariants as generation constraints (feed them to the LLM
   during translation, not just after).

---

## Appendix A — Witness Examples

Three concrete witnesses, shown as actual data tables.

**A.1 RETAIN_RESET witness** (6 rows, all values = 1):
Two groups (A and B), each with 3 rows. The correct oracle resets the cumsum at the
start of group B, giving [1,2,3] then [1,2,3]. The broken translation computes a
global cumsum, giving [1,2,3,4,5,6]. At row 3 (first row of group B), oracle = 1,
broken = 4. Bug exposed.

**A.2 JOIN_TYPE witness** (3+3 rows):
Left table has keys 1, 2, 3. Right table has keys 2, 3, 4. The correct outer join
gives 4 rows (key 1 left-only, keys 2 and 3 matched, key 4 right-only). The wrong
inner join gives only 2 rows (keys 2 and 3). Keys 1 and 4 disappear silently.

**A.3 SORT_STABLE witness** (2 rows):
Both rows have primary_key = 1 but different secondary values. In theory, stable sort
should preserve their order; unstable sort might swap them. In practice, Python's
Timsort on 2 equal-key rows is deterministic, so the swap never happens. This is
why C3's certificate is invalid.

---

## Appendix B — Invariant Formal Definitions

Mathematical definitions of 8 of the confirmed invariants.

In plain English:

| Invariant | What it checks |
|---|---|
| ROW_PRESERVATION_NON_FILTER | Output has at least as many rows as input |
| ROW_EQUALITY_SORT | PROC SORT: output has exactly the same number of rows as input |
| COLUMN_SUPERSET | All input columns still exist in the output |
| SORT_KEY_SORTED | The sort key columns are in order in the output |
| FREQ_PERCENT_SUM_100 | PROC FREQ: the percent column sums to exactly 100 |
| GROUP_BOUNDARY_STRICT_SUBSET | FIRST./LAST.: output has fewer rows than input |
| OUTPUT_NONEMPTY | If input is non-empty, output is non-empty |
| COLUMN_DTYPE_STABILITY | Numeric columns in input remain numeric in output |

---

## Quick Reference: What Each Figure Shows

| Figure | Location | One-sentence summary |
|---|---|---|
| Figure 1 | §6 | The five validation layers stacked from top to bottom, each catching a different type of error |
| Figure 2 | §4.3 | The step-by-step flow from "error class" to "coverage certificate" through Z3 |
| Figure 3 | §7.3 | Bar chart comparing how often each testing method catches each bug type |
| Figure 4 | §4.1 | Tree grouping the 6 bug classes by root cause |

## Quick Reference: What Each Table Shows

| Table | Location | One-sentence summary |
|---|---|---|
| Taxonomy (Table 1 in paper) | §4.1 | The 6 error classes with their SAS trigger and common Python mistranslation |
| Datasets | §7.1 | The 3 evaluation datasets, their sizes, and what each is used for |
| CDAIS Summary | §7.3 | High-level comparison: random vs. heuristic vs. CDAIS across 4 dimensions |
| Per-Class Results | §7.3 | Detailed numbers for each of the 6 error classes |
| MIS Invariants | §7.4 | All 18 candidate invariants with their confirmation status and oracle pass rates |
| Z3 Results | §7.5 | Z3 formal verification results on 10-block torture test |
| LLM Benchmark | §7.6 | Translation quality of 2 AI models on 10 hard SAS blocks |
| Ablation | §7.7 | Comparison of random vs. heuristic vs. CDAIS data on 4 quality dimensions |
| Reproducibility | §7.8 | Script-to-result mapping so anyone can re-run every number |
