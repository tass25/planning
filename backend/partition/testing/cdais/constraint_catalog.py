"""constraint_catalog.py — Z3 constraint encoders for CDAIS error classes.

CDAIS (Constraint-Driven Adversarial Input Synthesis) encodes each known
SAS→Python semantic error class as a Z3 SMT constraint system.

For each error class, the catalog defines:
  - name          : identifier string
  - description   : what semantic error is being targeted
  - applicable_to : returns True if this class matches a given SAS code block
  - encode        : adds Z3 constraints to a Solver; returns symbolic variables
                    so the synthesizer can extract concrete values from a SAT model

The constraint systems encode the DIVERGENCE condition:
    correct_output(witness) ≠ incorrect_output(witness)

When Z3 finds a SAT assignment, the model gives a concrete minimum witness —
the smallest input DataFrame for which a correct and an incorrect translation
produce different results.

Error classes implemented:
  1. RETAIN_RESET       — cumsum must reset at BY-group boundaries
  2. LAG_QUEUE          — LAG(x) must yield NULL at first row of each group
  3. SORT_STABLE        — PROC SORT must be stable (equal-key rows preserve order)
  4. NULL_ARITHMETIC    — SAS missing (.) treated as 0 in accumulator, not NaN
  5. JOIN_TYPE          — MERGE without IN= is outer join, not inner join
  6. GROUP_BOUNDARY     — FIRST./LAST. are per-group markers, not whole-DF head/tail
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ConstraintConfig:
    """Parameters that control the size of the synthesis problem."""
    n_groups: int = 2          # number of BY-groups in the witness
    n_rows_per_group: int = 3  # rows per group
    value_min: int = 1         # minimum symbolic value
    value_max: int = 100       # maximum symbolic value
    z3_timeout_ms: int = 10_000


@dataclass
class EncodedConstraints:
    """Result of encoding: symbolic vars + the divergence constraint is already added."""
    sym_vars: dict[str, Any]    # name → z3 symbolic variable
    n_groups: int
    n_rows_per_group: int
    error_class: str


class ErrorClass:
    """Base class for all CDAIS error encoders."""

    name: str = ""
    description: str = ""

    def applicable_to(self, sas_code: str) -> bool:
        raise NotImplementedError

    def encode(self, solver: Any, cfg: ConstraintConfig) -> EncodedConstraints:
        raise NotImplementedError


# ── 1. RETAIN_RESET ───────────────────────────────────────────────────────────

class RetainResetError(ErrorClass):
    """Targets translations that do df.cumsum() without per-group reset.

    Correct:   cumsum resets at each FIRST. boundary → per-group running total
    Incorrect: global cumsum across all groups → values inflate after group 1

    Encoding:
      Symbolic values v[g][r] ∈ [1, max] for g ∈ groups, r ∈ rows_per_group.
      Correct cumsum at row r in group g: C[g][r] = Σ_{k=0}^{r} v[g][k]
      Incorrect global cumsum at global index i: IC[i] = Σ_{k=0}^{i} v[flat[k]]
      Divergence: C[1][0] ≠ IC[n_rows_per_group]   (first row of second group)
      Minimality: minimize Σ v[g][r]
    """

    name = "RETAIN_RESET"
    description = (
        "RETAIN accumulator must reset at each BY-group boundary (FIRST.). "
        "df.cumsum() without groupby misses the reset."
    )

    def applicable_to(self, sas_code: str) -> bool:
        has_retain = bool(re.search(r"\bretain\b", sas_code, re.IGNORECASE))
        has_by     = bool(re.search(r"\bby\b", sas_code, re.IGNORECASE))
        has_accum  = bool(re.search(r"\w+\s*\+\s*\w+", sas_code))
        return has_retain and (has_by or has_accum)

    def encode(self, solver: Any, cfg: ConstraintConfig) -> EncodedConstraints:
        import z3

        G = cfg.n_groups
        R = cfg.n_rows_per_group
        lo = z3.IntVal(cfg.value_min)
        hi = z3.IntVal(cfg.value_max)

        # Symbolic values: v[g][r]
        v = [[z3.Int(f"v_{g}_{r}") for r in range(R)] for g in range(G)]

        # Domain constraints
        for g in range(G):
            for r in range(R):
                solver.add(v[g][r] >= lo, v[g][r] <= hi)

        # Correct per-group cumsum
        C = [[z3.IntVal(0)] * R for _ in range(G)]
        for g in range(G):
            running = z3.IntVal(0)
            for r in range(R):
                running = running + v[g][r]
                C[g][r] = running

        # Incorrect global cumsum (no reset)
        flat = [v[g][r] for g in range(G) for r in range(R)]
        IC = []
        running = z3.IntVal(0)
        for val in flat:
            running = running + val
            IC.append(running)

        # Divergence: first row of group 1 must differ
        # C[1][0] = v[1][0]
        # IC[R] = Σ v[0][0..R-1] + v[1][0]  ← this equals C[0][R-1] + v[1][0]
        # They differ iff C[0][R-1] ≠ 0 iff Σ v[0][0..R-1] > 0 (always true since lo≥1)
        solver.add(C[1][0] != IC[R])  # always SAT for lo≥1, but Z3 gives minimum

        sym_vars = {f"v_{g}_{r}": v[g][r] for g in range(G) for r in range(R)}
        return EncodedConstraints(sym_vars=sym_vars, n_groups=G,
                                  n_rows_per_group=R, error_class=self.name)


# ── 2. LAG_QUEUE ──────────────────────────────────────────────────────────────

class LagQueueError(ErrorClass):
    """Targets translations using shift(1) instead of per-group-reset LAG.

    Correct:   LAG(x)[first row of group g] = NULL (queue empties at boundary)
    Incorrect: shift(1)[first row of group g] = last value of group g-1

    Encoding:
      v[r] for r ∈ [0, G*R).  Group boundary at index R.
      Correct:  lag_correct[R] = NULL  (group boundary reset)
      Incorrect: lag_wrong[R]  = v[R-1]  (shift carries over)
      Divergence: v[R-1] ≠ 0   (boundary value must be non-zero to be visible)
    """

    name = "LAG_QUEUE"
    description = (
        "LAG(x) must yield NULL at the first row of each BY-group. "
        "shift(1) instead carries the last value of the previous group."
    )

    def applicable_to(self, sas_code: str) -> bool:
        return bool(re.search(r"\blag\s*\(", sas_code, re.IGNORECASE))

    def encode(self, solver: Any, cfg: ConstraintConfig) -> EncodedConstraints:
        import z3

        R = cfg.n_rows_per_group
        lo = z3.IntVal(cfg.value_min)
        hi = z3.IntVal(cfg.value_max)

        # Symbolic values for two groups
        v = [z3.Int(f"lag_v_{i}") for i in range(2 * R)]
        for vi in v:
            solver.add(vi >= lo, vi <= hi)

        # Boundary value v[R-1] is the last row of group 0.
        # shift(1) at index R yields v[R-1].
        # correct LAG at index R yields NULL (represented as 0 for comparison).
        # Divergence requires v[R-1] ≠ 0 — guaranteed since lo ≥ 1.
        boundary_val = v[R - 1]
        null_sentinel = z3.IntVal(0)  # NULL encoded as 0 in our integer domain
        solver.add(boundary_val != null_sentinel)   # always SAT

        sym_vars = {f"lag_v_{i}": v[i] for i in range(2 * R)}
        return EncodedConstraints(sym_vars=sym_vars, n_groups=2,
                                  n_rows_per_group=R, error_class=self.name)


# ── 3. SORT_STABLE ────────────────────────────────────────────────────────────

class SortStableError(ErrorClass):
    """Targets translations using sort_values without kind='mergesort'.

    PROC SORT is always stable: equal-key rows preserve original order.
    Unstable sort may swap equal-key rows.

    Encoding:
      Two rows with equal primary key k1 == k2.
      Different secondary values s1 ≠ s2.
      Original order: row 0 before row 1.
      Stable sort: row 0 still before row 1 (order preserved).
      Unstable sort: either order permitted (non-deterministic).
      Witness: k1 == k2  AND  s1 ≠ s2  (minimal: s1=1, s2=2, key=1)
    """

    name = "SORT_STABLE"
    description = (
        "PROC SORT is always stable. sort_values() without kind='mergesort' "
        "may produce wrong order for equal-key rows."
    )

    def applicable_to(self, sas_code: str) -> bool:
        return bool(re.search(r"\bproc\s+sort\b", sas_code, re.IGNORECASE))

    def encode(self, solver: Any, cfg: ConstraintConfig) -> EncodedConstraints:
        import z3

        key1 = z3.Int("sort_key1")
        key2 = z3.Int("sort_key2")
        sec1 = z3.Int("sort_sec1")
        sec2 = z3.Int("sort_sec2")

        lo = z3.IntVal(cfg.value_min)
        hi = z3.IntVal(cfg.value_max)

        for v in (key1, key2, sec1, sec2):
            solver.add(v >= lo, v <= hi)

        # Equal primary keys, distinct secondary values
        solver.add(key1 == key2)
        solver.add(sec1 != sec2)

        sym_vars = {
            "sort_key1": key1, "sort_key2": key2,
            "sort_sec1": sec1, "sort_sec2": sec2,
        }
        return EncodedConstraints(sym_vars=sym_vars, n_groups=1,
                                  n_rows_per_group=2, error_class=self.name)


# ── 4. NULL_ARITHMETIC ────────────────────────────────────────────────────────

class NullArithmeticError(ErrorClass):
    """Targets RETAIN accumulators that don't handle SAS missing (.) as 0.

    SAS: total + . → total (missing treated as additive identity)
    Python: total + NaN → NaN (NaN propagates in arithmetic)

    Encoding:
      Symbolic accumulator total, addend x, missing flag is_missing.
      If is_missing: correct_result = total, wrong_result = NaN-sentinel (-999)
      Divergence: is_missing=True AND total ≠ -999
    """

    name = "NULL_ARITHMETIC"
    description = (
        "SAS treats missing (.) as 0 in RETAIN sum accumulator. "
        "pandas NaN propagates — .fillna(0) required before accumulation."
    )

    def applicable_to(self, sas_code: str) -> bool:
        has_retain = bool(re.search(r"\bretain\b", sas_code, re.IGNORECASE))
        has_accum  = bool(re.search(r"\w+\s*\+\s*\w+", sas_code))
        return has_retain and has_accum

    def encode(self, solver: Any, cfg: ConstraintConfig) -> EncodedConstraints:
        import z3

        total      = z3.Int("null_total")
        addend     = z3.Int("null_addend")
        is_missing = z3.Bool("null_is_missing")

        lo = z3.IntVal(cfg.value_min)
        hi = z3.IntVal(cfg.value_max)
        nan_sentinel = z3.IntVal(-999)

        solver.add(total  >= lo, total  <= hi)
        solver.add(addend >= lo, addend <= hi)

        # Correct result when is_missing: total unchanged
        correct_result = z3.If(is_missing, total, total + addend)
        # Wrong result when is_missing: NaN propagation → sentinel
        wrong_result   = z3.If(is_missing, nan_sentinel, total + addend)

        # Diverge only when is_missing is True
        solver.add(is_missing == True)
        solver.add(correct_result != wrong_result)  # total ≠ -999, always SAT

        sym_vars = {
            "null_total": total,
            "null_addend": addend,
            "null_is_missing": is_missing,
        }
        return EncodedConstraints(sym_vars=sym_vars, n_groups=2,
                                  n_rows_per_group=cfg.n_rows_per_group,
                                  error_class=self.name)


# ── 5. JOIN_TYPE ──────────────────────────────────────────────────────────────

class JoinTypeError(ErrorClass):
    """Targets MERGE translated as inner join instead of outer join.

    SAS DATA step MERGE (without IN= subsetting IF) is an outer join:
    ALL rows from BOTH tables appear in the output.
    Pandas merge defaults to how='inner', silently dropping non-matching rows.

    Encoding:
      |L| rows in left table with keys K_L ⊂ Z.
      |R| rows in right table with keys K_R ⊂ Z.
      Require K_L ≠ K_R (asymmetric match — some keys in L not in R, vice versa).
      Correct output rows = |K_L ∪ K_R|
      Wrong output rows   = |K_L ∩ K_R|
      Diverge:  |K_L ∪ K_R| ≠ |K_L ∩ K_R|  ←  always true when K_L ≠ K_R
    """

    name = "JOIN_TYPE"
    description = (
        "SAS DATA MERGE is an outer join. pd.merge() defaults to inner join, "
        "silently dropping non-matching rows from either table."
    )

    def applicable_to(self, sas_code: str) -> bool:
        has_merge = bool(re.search(r"\bmerge\b", sas_code, re.IGNORECASE))
        # Only fire if there is NO IN= subsetting IF (which makes it a filtered join)
        has_in_filter = bool(re.search(r"\bif\s+\w+\s*;", sas_code, re.IGNORECASE))
        return has_merge and not has_in_filter

    def encode(self, solver: Any, cfg: ConstraintConfig) -> EncodedConstraints:
        import z3

        # Keys for left table: k_L[0], k_L[1], ...
        # Keys for right table: k_R[0], k_R[1], ...
        # We use 3 keys in L and 3 in R with different values to ensure asymmetry
        n = cfg.n_rows_per_group  # keys per table

        k_L = [z3.Int(f"join_kL_{i}") for i in range(n)]
        k_R = [z3.Int(f"join_kR_{i}") for i in range(n)]

        lo = z3.IntVal(1)
        hi = z3.IntVal(n * 4)

        for k in k_L + k_R:
            solver.add(k >= lo, k <= hi)

        # All keys within each table are distinct
        solver.add(z3.Distinct(*k_L))
        solver.add(z3.Distinct(*k_R))

        # At least one key in L not in R (non-matching left row exists)
        # Encode: k_L[0] ∉ {k_R[0], ..., k_R[n-1]}
        solver.add(z3.And([k_L[0] != k_R[j] for j in range(n)]))

        # At least one key in R not in L (non-matching right row exists)
        solver.add(z3.And([k_R[0] != k_L[j] for j in range(n)]))

        sym_vars = {
            **{f"join_kL_{i}": k_L[i] for i in range(n)},
            **{f"join_kR_{i}": k_R[i] for i in range(n)},
        }
        return EncodedConstraints(sym_vars=sym_vars, n_groups=2,
                                  n_rows_per_group=n, error_class=self.name)


# ── 6. GROUP_BOUNDARY ─────────────────────────────────────────────────────────

class GroupBoundaryError(ErrorClass):
    """Targets FIRST./LAST. implemented as .head(1)/.tail(1) on the full DF.

    Correct:   FIRST.var = first row within each BY-group
    Incorrect: df.head(1) = only the very first row of the entire DataFrame

    With ≥2 groups, the first row of group 1 is visible in the correct output
    but NOT in the incorrect .head(1) output.

    Encoding:
      G groups, R rows each.
      Correct rows = {(g, 0) for g in range(G)}  (G rows)
      Wrong rows   = {(0, 0)}                     (1 row)
      Divergence:  G ≠ 1  →  always SAT for G ≥ 2
    """

    name = "GROUP_BOUNDARY"
    description = (
        "FIRST.var selects the first row of EACH BY-group. "
        "df.head(1) only selects the first row of the entire DataFrame."
    )

    def applicable_to(self, sas_code: str) -> bool:
        has_first_last = bool(re.search(r"\bfirst\.\w+|\blast\.\w+", sas_code, re.IGNORECASE))
        has_by         = bool(re.search(r"\bby\b", sas_code, re.IGNORECASE))
        return has_first_last and has_by

    def encode(self, solver: Any, cfg: ConstraintConfig) -> EncodedConstraints:
        import z3

        G = cfg.n_groups
        R = cfg.n_rows_per_group

        # Group labels and row values
        group_labels = [z3.Int(f"gb_group_{g}") for g in range(G)]
        row_vals     = [[z3.Int(f"gb_val_{g}_{r}") for r in range(R)] for g in range(G)]

        lo = z3.IntVal(cfg.value_min)
        hi = z3.IntVal(cfg.value_max)

        for g in range(G):
            solver.add(group_labels[g] >= lo, group_labels[g] <= hi)
            for r in range(R):
                solver.add(row_vals[g][r] >= lo, row_vals[g][r] <= hi)

        # Groups must have distinct labels
        solver.add(z3.Distinct(*group_labels))

        # Divergence: correct output has G rows, wrong has 1.
        # For G ≥ 2 this is always satisfiable.
        n_correct = z3.IntVal(G)
        n_wrong   = z3.IntVal(1)
        solver.add(n_correct != n_wrong)  # trivially SAT for G≥2

        sym_vars = {
            **{f"gb_group_{g}": group_labels[g] for g in range(G)},
            **{f"gb_val_{g}_{r}": row_vals[g][r] for g in range(G) for r in range(R)},
        }
        return EncodedConstraints(sym_vars=sym_vars, n_groups=G,
                                  n_rows_per_group=R, error_class=self.name)


# ── Catalog registry ──────────────────────────────────────────────────────────

ALL_ERROR_CLASSES: list[ErrorClass] = [
    RetainResetError(),
    LagQueueError(),
    SortStableError(),
    NullArithmeticError(),
    JoinTypeError(),
    GroupBoundaryError(),
]

ERROR_CLASS_MAP: dict[str, ErrorClass] = {ec.name: ec for ec in ALL_ERROR_CLASSES}


def applicable_classes(sas_code: str) -> list[ErrorClass]:
    """Return all error classes whose triggers match this SAS code block."""
    return [ec for ec in ALL_ERROR_CLASSES if ec.applicable_to(sas_code)]
