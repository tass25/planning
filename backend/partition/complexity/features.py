"""Feature extraction for ComplexityAgent.

Extracts 14 numeric features from a PartitionIR block for use by
the LogReg + Platt complexity classifier.

Features 1-6 are structural; 7-14 are SAS-specific pattern detectors
that capture constructs known to increase translation difficulty.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from partition.models.enums import PartitionType
from partition.models.partition_ir import PartitionIR

# Type → raw complexity weight (higher = more complex)
_TYPE_WEIGHT: dict[PartitionType, float] = {
    PartitionType.MACRO_DEFINITION: 2.5,
    PartitionType.SQL_BLOCK: 2.0,
    PartitionType.CONDITIONAL_BLOCK: 1.8,
    PartitionType.LOOP_BLOCK: 1.8,
    PartitionType.DATA_STEP: 1.2,
    PartitionType.PROC_BLOCK: 1.0,
    PartitionType.MACRO_INVOCATION: 1.0,
    PartitionType.GLOBAL_STATEMENT: 0.2,
    PartitionType.INCLUDE_REFERENCE: 0.3,
    PartitionType.UNCLASSIFIED: 0.8,
}

# Normalisation denominators (keep features roughly in [0, 1])
_LINE_NORM = 200.0
_NEST_NORM = 5.0
_MACRO_NORM = 1.5

# Pattern detectors for SAS-specific complexity signals
_CALL_EXECUTE_RE = re.compile(r"\bCALL\s+EXECUTE\b", re.IGNORECASE)
_RETAIN_RE = re.compile(r"\bRETAIN\b", re.IGNORECASE)
_FIRST_LAST_RE = re.compile(r"\b(?:FIRST|LAST)\.\w+", re.IGNORECASE)
_MERGE_RE = re.compile(r"\bMERGE\b\s+\w+", re.IGNORECASE)
_HASH_RE = re.compile(
    r"\b(?:DECLARE\s+HASH|_new_\s*=\s*hash|\.definekey|\.definedata|\.definedone)\b", re.IGNORECASE
)
_ARRAY_RE = re.compile(r"\bARRAY\s+\w+", re.IGNORECASE)
_SQL_SUBQUERY_RE = re.compile(r"\(\s*SELECT\b", re.IGNORECASE)
_CALL_SYMPUT_RE = re.compile(r"\bCALL\s+SYMPUT(?:X)?\b", re.IGNORECASE)
_PROC_SQL_RE = re.compile(r"\bPROC\s+SQL\b", re.IGNORECASE)
_PROC_TRANSPOSE_RE = re.compile(r"\bPROC\s+TRANSPOSE\b", re.IGNORECASE)
_PROC_REPORT_RE = re.compile(r"\bPROC\s+REPORT\b", re.IGNORECASE)
_OUTPUT_RE = re.compile(r"\bOUTPUT\b", re.IGNORECASE)
_MACRO_DEF_RE = re.compile(r"%MACRO\b", re.IGNORECASE)
_DO_LOOP_RE = re.compile(r"\b(?:%DO|DO\s+\w+\s*=)", re.IGNORECASE)
_IF_THEN_RE = re.compile(r"\bIF\b.*\bTHEN\b", re.IGNORECASE)
_NESTING_OPEN_RE = re.compile(r"\b(?:DO\b|%DO\b|SELECT\b|IF\b.*\bTHEN\s+DO\b)", re.IGNORECASE)
_NESTING_CLOSE_RE = re.compile(r"\bEND\b\s*;", re.IGNORECASE)
_DATASET_REF_RE = re.compile(
    r"\b(?:DATA|SET|MERGE|FROM|INTO|UPDATE)\s+(\w+(?:\.\w+)?)", re.IGNORECASE
)


def _compute_nesting_depth(code: str) -> int:
    """Compute max nesting depth from source code directly."""
    depth = 0
    max_depth = 0
    for line in code.splitlines():
        line.strip().upper()
        opens = len(_NESTING_OPEN_RE.findall(line))
        closes = len(_NESTING_CLOSE_RE.findall(line))
        depth += opens
        max_depth = max(max_depth, depth)
        depth = max(0, depth - closes)
    return max_depth


def _count_distinct_datasets(code: str) -> int:
    """Count distinct dataset references in the code."""
    matches = _DATASET_REF_RE.findall(code)
    return len(
        set(
            m.lower()
            for m in matches
            if m.lower()
            not in (
                "_null_",
                "work",
                "_last_",
                "_data_",
            )
        )
    )


@dataclass(frozen=True)
class BlockFeatures:
    """Numerical feature vector for one PartitionIR block.

    14 features: 6 structural + 8 SAS-specific pattern indicators.
    All values are >= 0; values >1 are valid (soft normalisation only).
    """

    line_count_norm: float  # (line_end - line_start + 1) / 200
    nesting_depth_norm: float  # max nesting depth / 5
    macro_pct: float  # '%' occurrences / line_count
    has_call_execute: float  # CALL EXECUTE present
    type_weight: float  # partition type weight (0.2 – 2.5)
    is_ambiguous: float  # block flagged ambiguous
    has_retain_first_last: float  # RETAIN or FIRST./LAST. pattern
    has_merge_hash: float  # MERGE or hash object join
    has_sql_subquery: float  # nested SELECT in PROC SQL
    has_array_loop: float  # ARRAY processing or complex DO loops
    dataset_count_norm: float  # distinct dataset references / 5
    has_call_symput: float  # CALL SYMPUT/SYMPUTX (macro-data bridge)
    conditional_density: float  # IF-THEN count / line_count
    has_complex_proc: float  # TRANSPOSE / REPORT / complex PROC

    def to_list(self) -> list[float]:
        return [
            self.line_count_norm,
            self.nesting_depth_norm,
            self.macro_pct,
            self.has_call_execute,
            self.type_weight,
            self.is_ambiguous,
            self.has_retain_first_last,
            self.has_merge_hash,
            self.has_sql_subquery,
            self.has_array_loop,
            self.dataset_count_norm,
            self.has_call_symput,
            self.conditional_density,
            self.has_complex_proc,
        ]


def extract(partition: PartitionIR) -> BlockFeatures:
    """Extract features from a single PartitionIR block."""
    line_count = max(partition.line_end - partition.line_start + 1, 1)
    code = partition.source_code
    code.upper()

    # Nesting: compute from code directly, fall back to metadata
    nesting_from_meta = partition.metadata.get("nesting_depth", 0) or 0
    nesting_from_code = _compute_nesting_depth(code)
    nesting = max(nesting_from_meta, nesting_from_code)

    ambiguous = partition.metadata.get("is_ambiguous", False)

    macro_count = code.count("%")
    has_ce = bool(_CALL_EXECUTE_RE.search(code))
    macro_pct = min(macro_count / line_count, _MACRO_NORM)

    # SAS-specific pattern detection
    has_retain = bool(_RETAIN_RE.search(code))
    has_first_last = bool(_FIRST_LAST_RE.search(code))
    has_merge = bool(_MERGE_RE.search(code))
    has_hash = bool(_HASH_RE.search(code))
    has_sql_sub = bool(_SQL_SUBQUERY_RE.search(code))
    has_array = bool(_ARRAY_RE.search(code))
    has_do_loop = bool(_DO_LOOP_RE.search(code))
    has_symput = bool(_CALL_SYMPUT_RE.search(code))
    has_transpose = bool(_PROC_TRANSPOSE_RE.search(code))
    has_report = bool(_PROC_REPORT_RE.search(code))
    if_count = len(_IF_THEN_RE.findall(code))
    dataset_count = _count_distinct_datasets(code)

    return BlockFeatures(
        line_count_norm=line_count / _LINE_NORM,
        nesting_depth_norm=nesting / _NEST_NORM,
        macro_pct=macro_pct,
        has_call_execute=1.0 if has_ce else 0.0,
        type_weight=_TYPE_WEIGHT.get(partition.partition_type, 1.0),
        is_ambiguous=1.0 if ambiguous else 0.0,
        has_retain_first_last=1.0 if (has_retain or has_first_last) else 0.0,
        has_merge_hash=1.0 if (has_merge or has_hash) else 0.0,
        has_sql_subquery=1.0 if has_sql_sub else 0.0,
        has_array_loop=1.0 if (has_array or has_do_loop) else 0.0,
        dataset_count_norm=min(dataset_count / 5.0, 1.5),
        has_call_symput=1.0 if has_symput else 0.0,
        conditional_density=min(if_count / max(line_count, 1), 1.0),
        has_complex_proc=1.0 if (has_transpose or has_report) else 0.0,
    )
