"""Feature extraction for ComplexityAgent.

Extracts 6 numeric features from a PartitionIR block for use by
the LogReg + Platt complexity classifier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from partition.models.enums import PartitionType
from partition.models.partition_ir import PartitionIR

# Type → raw complexity weight (higher = more complex)
_TYPE_WEIGHT: dict[PartitionType, float] = {
    PartitionType.MACRO_DEFINITION:  2.0,
    PartitionType.SQL_BLOCK:         1.5,
    PartitionType.CONDITIONAL_BLOCK: 1.5,
    PartitionType.LOOP_BLOCK:        1.5,
    PartitionType.DATA_STEP:         1.0,
    PartitionType.PROC_BLOCK:        1.0,
    PartitionType.MACRO_INVOCATION:  0.5,
    PartitionType.GLOBAL_STATEMENT:  0.2,
    PartitionType.INCLUDE_REFERENCE: 0.2,
}

# Normalisation denominators (keep features roughly in [0, 1])
_LINE_NORM = 200.0
_NEST_NORM = 5.0
_MACRO_NORM = 1.5    # macro_pct rarely exceeds 1.5 per line

_CALL_EXECUTE_RE = re.compile(r"\bCALL\s+EXECUTE\b", re.IGNORECASE)
_NESTED_MACRO_RE = re.compile(r"%\w+\s*\(", re.IGNORECASE)


@dataclass(frozen=True)
class BlockFeatures:
    """Numerical feature vector for one PartitionIR block.

    These six scalar features drive the LogReg complexity classifier.
    All values are ≥ 0; values >1 are valid (soft normalisation only).
    """
    line_count_norm:    float   # (line_end - line_start + 1) / 200
    nesting_depth_norm: float   # nesting_depth / 5
    macro_pct:          float   # '%' occurrences / line_count  (capped at 1.5)
    has_call_execute:   float   # 1.0 if CALL EXECUTE found else 0.0
    type_weight:        float   # _TYPE_WEIGHT lookup (0.2 – 2.0)
    is_ambiguous:       float   # 1.0 if block flagged ambiguous else 0.0

    def to_list(self) -> list[float]:
        return [
            self.line_count_norm,
            self.nesting_depth_norm,
            self.macro_pct,
            self.has_call_execute,
            self.type_weight,
            self.is_ambiguous,
        ]


def extract(partition: PartitionIR) -> BlockFeatures:
    """Extract features from a single PartitionIR block."""
    line_count = max(partition.line_end - partition.line_start + 1, 1)
    nesting    = partition.metadata.get("nesting_depth", 0) or 0
    ambiguous  = partition.metadata.get("is_ambiguous", False)

    code = partition.source_code
    macro_count = code.count("%")
    has_ce      = bool(_CALL_EXECUTE_RE.search(code))
    macro_pct   = min(macro_count / line_count, _MACRO_NORM)

    return BlockFeatures(
        line_count_norm    = line_count  / _LINE_NORM,
        nesting_depth_norm = nesting     / _NEST_NORM,
        macro_pct          = macro_pct,
        has_call_execute   = 1.0 if has_ce else 0.0,
        type_weight        = _TYPE_WEIGHT.get(partition.partition_type, 1.0),
        is_ambiguous       = 1.0 if ambiguous else 0.0,
    )
