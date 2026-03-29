"""PartitionBuilderAgent — converts BlockBoundaryEvents into PartitionIR objects.

This is the final step of the L2-C chunking layer.
RAPTOR fields (raptor_leaf_id, cluster_id, root_id) are populated in Week 5-6.
Risk / complexity fields are populated by ComplexityAgent + StrategyAgent in Week 4.
"""

from __future__ import annotations

import hashlib
import re
from uuid import UUID

from partition.base_agent import BaseAgent

# Regex to extract PROC subtype, e.g. PROC MEANS → "MEANS"
_PROC_SUBTYPE_RE = re.compile(r"^\s*PROC\s+(\w+)", re.IGNORECASE | re.MULTILINE)
from partition.models.enums import PartitionType, RiskLevel, ConversionStatus
from partition.models.partition_ir import PartitionIR

from .models import BlockBoundaryEvent


class PartitionBuilderAgent(BaseAgent):
    """Build PartitionIR objects from a list of BlockBoundaryEvents.

    Input:  ``list[BlockBoundaryEvent]``  (output of BoundaryDetectorAgent)
    Output: ``list[PartitionIR]``         (ready for persistence + complexity scoring)

    Fields populated here:
        file_id, partition_type, source_code,
        line_start, line_end, metadata (chunking metadata),
        risk_level=UNCERTAIN (placeholder — overwritten by StrategyAgent).

    Fields intentionally left at defaults:
        risk_level          → overwritten by ComplexityAgent + StrategyAgent (Week 4)
        conversion_status   → starts at HUMAN_REVIEW, updated by ValidationAgent (Week ?)
        dependencies        → populated by IndexAgent using NetworkX SCC (Week 7)
    """

    agent_name = "PartitionBuilderAgent"

    async def process(  # type: ignore[override]
        self,
        events: list[BlockBoundaryEvent],
    ) -> list[PartitionIR]:
        """Convert boundary events to PartitionIR objects.

        Args:
            events: Sorted list from BoundaryDetectorAgent.process().

        Returns:
            List of PartitionIR objects, same order as input events.
        """
        partitions: list[PartitionIR] = []

        for event in events:
            content_hash = hashlib.sha256(
                event.raw_code.encode("utf-8")
            ).hexdigest()

            partition = PartitionIR(
                file_id=event.file_id,
                partition_type=event.partition_type,
                source_code=event.raw_code,
                line_start=event.line_start,
                line_end=event.line_end,
                risk_level=RiskLevel.UNCERTAIN,           # Week 4: ComplexityAgent
                conversion_status=ConversionStatus.HUMAN_REVIEW,
                dependencies=[],                          # Week 7: IndexAgent
                metadata={
                    # ── Chunking provenance ──────────────────────────────────
                    "content_hash":        content_hash,
                    "boundary_method":     event.boundary_method,
                    "confidence":          event.confidence,
                    "is_ambiguous":        event.is_ambiguous,
                    "nesting_depth":       event.nesting_depth,
                    "macro_scope":         event.macro_scope,
                    "variable_scope":      event.variable_scope,
                    "dependency_refs":     event.dependency_refs,
                    "test_coverage_type":  event.test_coverage_type,
                    "trace_id":            str(event.trace_id) if event.trace_id else None,
                    # ── RAPTOR placeholders (Week 5-6) ───────────────────────
                    "raptor_leaf_id":      None,
                    "raptor_cluster_id":   None,
                    "raptor_root_id":      None,
                    "raptor_summary_tier": None,
                    # ── PROC sub-classification ──────────────────────────────
                    # Prefer boundary_detector's direct extraction; fall back to regex.
                    "proc_subtype": (
                        event.extra_metadata.get("proc_type")
                        or self._extract_proc_subtype(event)
                    ),
                    # ── SCC / Graph placeholders (Week 7) ────────────────────
                    "scc_id":              None,
                },
            )
            partitions.append(partition)

        self.logger.info("partitions_built", count=len(partitions))
        return partitions

    @staticmethod
    def _extract_proc_subtype(event: BlockBoundaryEvent) -> str | None:
        """Extract PROC subtype (SORT, MEANS, REG, etc.) from source.

        Returns None if the block is not a PROC_BLOCK or no subtype found.
        """
        if event.partition_type not in (PartitionType.PROC_BLOCK, PartitionType.SQL_BLOCK):
            return None
        m = _PROC_SUBTYPE_RE.search(event.raw_code)
        return m.group(1).upper() if m else None
