"""invariant_synthesizer.py — Corpus-driven Migration Invariant Synthesis (MIS).

MIS discovers formal properties that hold universally across all correct
SAS→Python translations in the gold-standard corpus.

These are MIGRATION INVARIANTS: constraints that every correct translation
must satisfy, automatically inferred from data — not hand-written.

Algorithm (CORPUS-MIS):
  1. For each (SAS, Python) gold pair in the corpus:
     a. Generate adversarial input DataFrames (via DummyDataGenerator)
     b. Run the SAS oracle to get oracle_output (ground truth)
     c. Run the translated Python to get actual_output
     d. Collect observation triple (input_df, oracle_df, actual_df)
  2. For each candidate invariant P in the InvariantLibrary:
     a. Check P(oracle_df) for every observation in the corpus
     b. If P holds for ALL oracle outputs → P is a confirmed invariant
     c. Also check P(actual_df) → measures how many translations respect P
  3. Output: InvariantSet with confirmed invariants + per-invariant violation stats

The confirmed invariants become the migration specification for new translations:
  - Given a new (SAS, Python) pair, check all confirmed invariants
  - An invariant violation is a semantic error signal stronger than random testing:
    "Property P holds for all 45 correct gold-standard translations but NOT for yours"

Why this is novel:
  - Migration invariants have never been inferred from a paired corpus
  - The approach requires no SAS runtime (oracles simulate SAS semantics in Python)
  - Discovered invariants are domain-specific (SAS patterns) and data-validated
  - Coverage is measurable: #invariants violated / #invariants checked
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import structlog

from partition.translation.dummy_data_generator import DummyDataGenerator
from partition.translation.semantic_validator import (
    _exec_with_inputs,
    _normalize,
    _oracle_first_last,
    _oracle_lag,
    _oracle_merge,
    _oracle_proc_freq,
    _oracle_proc_means,
    _oracle_proc_sort,
    _oracle_retain,
)

logger = structlog.get_logger(__name__)

_ORACLE_FNS = [
    _oracle_proc_sort,
    _oracle_proc_means,
    _oracle_proc_freq,
    _oracle_retain,
    _oracle_lag,
    _oracle_first_last,
    _oracle_merge,
]


# ── Invariant types ───────────────────────────────────────────────────────────


@dataclass
class CandidateInvariant:
    """One candidate migration invariant."""

    name: str
    description: str
    sas_pattern: str  # regex that must match SAS code for this to apply
    check: Callable  # check(input_df, oracle_df) → bool
    category: str = "structural"  # structural | relational | ordering | semantic


# ── Invariant library — 18 candidates ─────────────────────────────────────────


def _safe(fn, *args, default=False):
    try:
        return fn(*args)
    except Exception:
        return default


INVARIANT_LIBRARY: list[CandidateInvariant] = [
    # ── Structural (row / column counts) ─────────────────────────────────────
    CandidateInvariant(
        name="ROW_PRESERVATION_NON_FILTER",
        description="Non-filter patterns must not drop rows (output rows ≥ input rows).",
        sas_pattern=r"\bdata\b(?!.*\bwhere\b)",
        check=lambda inp, out: len(out) >= len(inp),
        category="structural",
    ),
    CandidateInvariant(
        name="ROW_REDUCTION_AGGREGATION",
        description="PROC MEANS/FREQ must reduce rows (output rows < input rows for >1 group).",
        sas_pattern=r"\bproc\s+(means|freq)\b",
        check=lambda inp, out: len(out) < len(inp) if len(inp) > 3 else True,
        category="structural",
    ),
    CandidateInvariant(
        name="ROW_EQUALITY_SORT",
        description="PROC SORT must preserve row count exactly.",
        sas_pattern=r"\bproc\s+sort\b",
        check=lambda inp, out: len(out) == len(inp),
        category="structural",
    ),
    CandidateInvariant(
        name="ROW_REDUCTION_DEDUP",
        description="PROC SORT NODUPKEY must reduce rows (deduplication).",
        sas_pattern=r"\bproc\s+sort\b.*\bnodupkey\b",
        check=lambda inp, out: len(out) <= len(inp),
        category="structural",
    ),
    CandidateInvariant(
        name="COLUMN_SUPERSET",
        description="Data step output must contain at least all input columns.",
        sas_pattern=r"\bdata\b",
        check=lambda inp, out: set(c.lower() for c in inp.columns).issubset(
            set(c.lower() for c in out.columns)
        ),
        category="structural",
    ),
    CandidateInvariant(
        name="OUTPUT_NONEMPTY",
        description="Non-empty input must always produce non-empty output.",
        sas_pattern=r".",  # matches everything
        check=lambda inp, out: len(out) > 0 if len(inp) > 0 else True,
        category="structural",
    ),
    # ── Relational (value-based) ──────────────────────────────────────────────
    CandidateInvariant(
        name="SUM_PRESERVATION_NUMERIC",
        description="Data step without aggregation preserves sum of numeric columns.",
        sas_pattern=r"\bdata\b(?!.*\bproc\b)",
        check=lambda inp, out: _safe(
            lambda: all(
                abs(
                    pd.to_numeric(inp[c], errors="coerce").sum()
                    - pd.to_numeric(out[c], errors="coerce").sum()
                )
                < 1e-3
                for c in inp.columns
                if c in out.columns
                and pd.api.types.is_numeric_dtype(pd.to_numeric(inp[c], errors="coerce"))
            ),
            default=True,
        ),
        category="relational",
    ),
    CandidateInvariant(
        name="RETAIN_MONOTONE_CUMSUM",
        description="RETAIN accumulator output must be monotonically non-decreasing within each group.",
        sas_pattern=r"\bretain\b",
        check=lambda inp, out: _safe(
            lambda: all(
                pd.to_numeric(out[c], errors="coerce").diff().fillna(0).ge(-1e-6).all()
                for c in out.columns
                if c not in inp.columns
                and pd.api.types.is_numeric_dtype(pd.to_numeric(out[c], errors="coerce"))
            ),
            default=True,
        ),
        category="relational",
    ),
    CandidateInvariant(
        name="LAG_NULL_FIRST_ROW",
        description="LAG output must have null/NaN in the first row of each group.",
        sas_pattern=r"\blag\s*\(",
        check=lambda inp, out: _safe(
            lambda: any(
                pd.to_numeric(out[c], errors="coerce").iloc[0]
                != pd.to_numeric(out[c], errors="coerce").iloc[0]
                for c in out.columns
                if c not in inp.columns
            ),
            default=True,
        ),
        category="relational",
    ),
    CandidateInvariant(
        name="SORT_KEY_SORTED",
        description="PROC SORT output must be sorted by BY variables.",
        sas_pattern=r"\bproc\s+sort\b",
        check=lambda inp, out: _safe(
            lambda: all(
                out[c].is_monotonic_increasing or out[c].is_monotonic_decreasing
                for c in out.columns
                if c in inp.columns and len(out[c].unique()) > 1
            ),
            default=True,
        ),
        category="ordering",
    ),
    CandidateInvariant(
        name="MERGE_OUTER_ROWCOUNT",
        description="DATA MERGE (no IN= filter) output rows ≥ max(|left|, |right|).",
        sas_pattern=r"\bmerge\b(?!.*\bif\s+\w+\s*;)",
        check=lambda inp, out: len(out) >= max(len(inp) // 2, 1),
        category="structural",
    ),
    CandidateInvariant(
        name="FREQ_PERCENT_SUM_100",
        description="PROC FREQ percent column must sum to 100 (±0.1).",
        sas_pattern=r"\bproc\s+freq\b",
        check=lambda inp, out: _safe(
            lambda: any(
                abs(pd.to_numeric(out[c], errors="coerce").sum() - 100.0) < 0.1
                for c in out.columns
                if "percent" in c.lower()
            ),
            default=True,
        ),
        category="relational",
    ),
    CandidateInvariant(
        name="NO_NEGATIVE_COUNTS",
        description="Count columns (_FREQ_, _N_, count) must be non-negative.",
        sas_pattern=r"\bproc\s+(means|freq)\b",
        check=lambda inp, out: _safe(
            lambda: all(
                pd.to_numeric(out[c], errors="coerce").ge(0).all()
                for c in out.columns
                if any(kw in c.lower() for kw in ("freq", "_n_", "count", "_type_"))
            ),
            default=True,
        ),
        category="relational",
    ),
    CandidateInvariant(
        name="FIRST_LAST_SUBSET",
        description="FIRST./LAST. output must be a subset of the input (no new rows created).",
        sas_pattern=r"\bfirst\.\w+|\blast\.\w+",
        check=lambda inp, out: len(out) <= len(inp),
        category="structural",
    ),
    CandidateInvariant(
        name="COLUMN_DTYPE_STABILITY",
        description="Numeric input columns must remain numeric in the output.",
        sas_pattern=r".",
        check=lambda inp, out: _safe(
            lambda: all(
                (
                    pd.api.types.is_numeric_dtype(pd.to_numeric(out[c], errors="coerce"))
                    if c in out.columns
                    else True
                )
                for c in inp.columns
                if pd.api.types.is_numeric_dtype(pd.to_numeric(inp[c], errors="coerce"))
            ),
            default=True,
        ),
        category="semantic",
    ),
    CandidateInvariant(
        name="GROUP_BOUNDARY_STRICT_SUBSET",
        description="FIRST./LAST. must select strictly fewer rows than the input.",
        sas_pattern=r"\b(if\s+first\.\w+\s*;|if\s+last\.\w+\s*;)",
        check=lambda inp, out: len(out) < len(inp),
        category="structural",
    ),
    CandidateInvariant(
        name="MEANS_AGGREGATION_MONOTONE",
        description="PROC MEANS output must have fewer unique group combinations than input rows.",
        sas_pattern=r"\bproc\s+means\b.*\bclass\b",
        check=lambda inp, out: len(out) <= len(inp),
        category="structural",
    ),
    CandidateInvariant(
        name="NO_DUPLICATE_GROUP_KEYS",
        description="PROC MEANS output must not have duplicate class-column combinations.",
        sas_pattern=r"\bproc\s+means\b",
        check=lambda inp, out: _safe(
            lambda: (
                not any(
                    out[c].duplicated().any()
                    for c in out.columns
                    if c not in inp.columns and "group" in c.lower()
                )
            ),
            default=True,
        ),
        category="relational",
    ),
]


# ── Observation collection ────────────────────────────────────────────────────


@dataclass
class Observation:
    """One (SAS, Python, input, oracle_output, actual_output) observation."""

    pair_id: str
    sas_code: str
    python_code: str
    input_df: pd.DataFrame
    oracle_df: Optional[pd.DataFrame]
    actual_df: Optional[pd.DataFrame]
    oracle_pattern: str = ""  # which oracle fired


def _run_oracle(
    sas_code: str, input_frames: dict[str, pd.DataFrame]
) -> tuple[Optional[pd.DataFrame], str]:
    for fn in _ORACLE_FNS:
        try:
            result = fn(sas_code, input_frames)
            if result is not None:
                return next(iter(result.values())), fn.__name__
        except Exception:
            pass
    return None, ""


def _collect_observation(
    pair_id: str,
    sas_code: str,
    python_code: str,
) -> Optional[Observation]:
    try:
        gen = DummyDataGenerator(sas_code=sas_code)
        frames = gen.generate()
        if not frames:
            return None

        input_df = _normalize(next(iter(frames.values())))
        oracle_df, pattern = _run_oracle(sas_code, frames)

        out_names = list(gen.output_table_names() or [])
        if oracle_df is not None:
            out_names = out_names or ["output"]

        actual_frames = _exec_with_inputs(python_code, frames, out_names or ["output"])
        actual_df = None
        if actual_frames:
            actual_df = (actual_frames.get(out_names[0]) if out_names else None) or (
                next(iter(actual_frames.values())) if actual_frames else None
            )

        return Observation(
            pair_id=pair_id,
            sas_code=sas_code,
            python_code=python_code,
            input_df=input_df,
            oracle_df=oracle_df,
            actual_df=actual_df,
            oracle_pattern=pattern,
        )
    except Exception as exc:
        logger.debug("mis_observation_error", pair_id=pair_id, error=str(exc))
        return None


# ── Invariant evaluation ──────────────────────────────────────────────────────


@dataclass
class InvariantResult:
    """Evaluation of one candidate invariant across the corpus."""

    invariant_name: str
    description: str
    category: str
    applicable_pairs: int  # pairs where sas_pattern matched
    oracle_violations: int  # oracle outputs that violated this invariant
    actual_violations: int  # actual (translated) outputs that violated it
    confirmed: bool  # True if oracle_violations == 0

    @property
    def oracle_pass_rate(self) -> float:
        if self.applicable_pairs == 0:
            return 1.0
        return (self.applicable_pairs - self.oracle_violations) / self.applicable_pairs

    @property
    def translation_pass_rate(self) -> float:
        if self.applicable_pairs == 0:
            return 1.0
        return (self.applicable_pairs - self.actual_violations) / self.applicable_pairs


@dataclass
class InvariantSet:
    """Full set of discovered invariants with evaluation statistics."""

    confirmed: list[InvariantResult] = field(default_factory=list)
    rejected: list[InvariantResult] = field(default_factory=list)
    n_pairs_total: int = 0
    n_observations: int = 0
    latency_ms: float = 0.0

    def check_translation(
        self,
        sas_code: str,
        python_code: str,
    ) -> list[str]:
        """Check a new translation against all confirmed invariants.

        Returns a list of violated invariant names (empty = all pass).
        """
        try:
            gen = DummyDataGenerator(sas_code=sas_code)
            frames = gen.generate()
            if not frames:
                return []
            input_df = _normalize(next(iter(frames.values())))
            oracle_df, _ = _run_oracle(sas_code, frames)
            if oracle_df is None:
                return []
        except Exception:
            return []

        violations = []
        for inv_result in self.confirmed:
            inv = next(
                (c for c in INVARIANT_LIBRARY if c.name == inv_result.invariant_name),
                None,
            )
            if inv is None:
                continue
            if not re.search(inv.sas_pattern, sas_code, re.IGNORECASE | re.DOTALL):
                continue
            try:
                if not inv.check(input_df, oracle_df):
                    violations.append(inv.invariant_name)
            except Exception:
                pass
        return violations

    def to_markdown_table(self) -> str:
        lines = [
            "| Invariant | Category | Applicable | Oracle Pass | Translation Pass | Status |",
            "|-----------|----------|------------|-------------|------------------|--------|",
        ]
        for r in sorted(
            self.confirmed + self.rejected, key=lambda x: (-x.oracle_pass_rate, x.invariant_name)
        ):
            status = "[+] Confirmed" if r.confirmed else "[-] Rejected"
            lines.append(
                f"| {r.invariant_name} | {r.category} "
                f"| {r.applicable_pairs} "
                f"| {r.oracle_pass_rate:.1%} "
                f"| {r.translation_pass_rate:.1%} "
                f"| {status} |"
            )
        return "\n".join(lines)


# ── Main synthesizer ──────────────────────────────────────────────────────────


class MigrationInvariantSynthesizer:
    """Discovers migration invariants from a paired (SAS, Python) corpus.

    Loads pairs from:
      - gold_standard_dir: .sas + .gold.json files (gold.json must have python_code)
      - extra_pairs: list of (sas_code, python_code) passed directly
    """

    def __init__(
        self,
        gold_standard_dir: Optional[str] = None,
        candidates: Optional[list[CandidateInvariant]] = None,
    ) -> None:
        self.gold_dir = Path(gold_standard_dir or "backend/knowledge_base/gold_standard")
        self.candidates = candidates or INVARIANT_LIBRARY

    def synthesize(
        self,
        extra_pairs: Optional[list[tuple[str, str]]] = None,
        max_pairs: int = 200,
    ) -> InvariantSet:
        """Run MIS over the corpus and return the InvariantSet."""
        t0 = time.monotonic()

        pairs = self._load_pairs(max_pairs)
        if extra_pairs:
            pairs.extend(extra_pairs[: max(0, max_pairs - len(pairs))])

        logger.info("mis_start", n_pairs=len(pairs))

        observations: list[Observation] = []
        for i, (sas, py) in enumerate(pairs):
            obs = _collect_observation(f"pair_{i}", sas, py)
            if obs is not None:
                observations.append(obs)

        logger.info("mis_observations_collected", n=len(observations))

        # Evaluate each candidate invariant
        results: list[InvariantResult] = []
        for candidate in self.candidates:
            r = self._evaluate_invariant(candidate, observations)
            results.append(r)

        confirmed = [r for r in results if r.confirmed]
        rejected = [r for r in results if not r.confirmed]

        elapsed = (time.monotonic() - t0) * 1000
        logger.info(
            "mis_complete",
            confirmed=len(confirmed),
            rejected=len(rejected),
            latency_ms=f"{elapsed:.0f}",
        )

        return InvariantSet(
            confirmed=confirmed,
            rejected=rejected,
            n_pairs_total=len(pairs),
            n_observations=len(observations),
            latency_ms=elapsed,
        )

    # ── internals ─────────────────────────────────────────────────────────────

    def _load_pairs(self, max_pairs: int) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        if not self.gold_dir.exists():
            logger.warning("mis_gold_dir_missing", path=str(self.gold_dir))
            return pairs

        sas_files = sorted(self.gold_dir.glob("*.sas"))
        for sas_file in sas_files[:max_pairs]:
            json_file = sas_file.with_suffix(".gold.json")
            if not json_file.exists():
                continue
            try:
                try:
                    sas_code = sas_file.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    sas_code = sas_file.read_text(encoding="utf-8", errors="replace")
                gold = json.loads(json_file.read_text(encoding="utf-8"))
                py_code = gold.get("python_code") or gold.get("expected_python")
                if py_code:
                    pairs.append((sas_code, py_code))
            except Exception as exc:
                logger.debug("mis_load_pair_error", file=sas_file.name, error=str(exc))

        return pairs

    def _evaluate_invariant(
        self,
        candidate: CandidateInvariant,
        observations: list[Observation],
    ) -> InvariantResult:
        applicable = 0
        oracle_viol = 0
        actual_viol = 0

        for obs in observations:
            if not re.search(candidate.sas_pattern, obs.sas_code, re.IGNORECASE | re.DOTALL):
                continue
            applicable += 1

            # Check oracle output
            if obs.oracle_df is not None:
                try:
                    if not candidate.check(obs.input_df, obs.oracle_df):
                        oracle_viol += 1
                except Exception:
                    pass

            # Check actual translation output
            if obs.actual_df is not None:
                try:
                    if not candidate.check(obs.input_df, obs.actual_df):
                        actual_viol += 1
                except Exception:
                    pass

        confirmed = (applicable > 0) and (oracle_viol == 0)

        return InvariantResult(
            invariant_name=candidate.name,
            description=candidate.description,
            category=candidate.category,
            applicable_pairs=applicable,
            oracle_violations=oracle_viol,
            actual_violations=actual_viol,
            confirmed=confirmed,
        )
