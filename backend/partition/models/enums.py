"""Enums used across the partition pipeline."""

from __future__ import annotations

from enum import Enum


class PartitionType(str, Enum):
    """SAS block types recognised by the partitioner."""
    DATA_STEP = "DATA_STEP"
    PROC_BLOCK = "PROC_BLOCK"
    MACRO_DEFINITION = "MACRO_DEFINITION"
    MACRO_INVOCATION = "MACRO_INVOCATION"
    SQL_BLOCK = "SQL_BLOCK"
    CONDITIONAL_BLOCK = "CONDITIONAL_BLOCK"
    LOOP_BLOCK = "LOOP_BLOCK"
    GLOBAL_STATEMENT = "GLOBAL_STATEMENT"
    INCLUDE_REFERENCE = "INCLUDE_REFERENCE"
    UNCLASSIFIED = "UNCLASSIFIED"


class RiskLevel(str, Enum):
    """Conversion risk assessment."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    UNCERTAIN = "UNCERTAIN"


class ConversionStatus(str, Enum):
    """Status of a converted block or file."""
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class PartitionStrategy(str, Enum):
    """Strategy used to partition a SAS file."""
    FLAT_PARTITION = "FLAT_PARTITION"
    MACRO_AWARE = "MACRO_AWARE"
    DEPENDENCY_PRESERVING = "DEPENDENCY_PRESERVING"
    STRUCTURAL_GROUPING = "STRUCTURAL_GROUPING"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class VerificationStatus(str, Enum):
    """Semantic equivalence verification result (Z3 / Oracle)."""
    FORMAL_PROOF = "formal_proof"       # Z3 proved equivalent
    BEHAVIORALLY_VERIFIED = "behavioral_verified"  # Oracle passed (Month 2)
    COUNTEREXAMPLE = "counterexample"   # Z3/Oracle found a difference → re-queue
    UNVERIFIABLE = "unverifiable"       # Outside decidable scope
    SKIPPED = "skipped"                 # Feature flag disabled
