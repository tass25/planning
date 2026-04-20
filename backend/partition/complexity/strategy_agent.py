"""StrategyAgent — L2-D conversion-strategy selection.

Maps each ``PartitionIR`` block's ``RiskLevel`` (set by ComplexityAgent) to a
``PartitionStrategy`` that controls how the TranslationAgent (L3) will handle it.

Routing table (risk level × partition type)
-------------------------------------------
LOW
  DATA_STEP, PROC_BLOCK, GLOBAL_STATEMENT, INCLUDE_REFERENCE
      → FLAT_PARTITION      (direct template substitution; no macro context)
  SQL_BLOCK
      → DEPENDENCY_PRESERVING  (preserve lineage even for simple SQL)
  MACRO_DEFINITION, MACRO_INVOCATION, CONDITIONAL_BLOCK, LOOP_BLOCK
      → MACRO_AWARE            (macro context must be threaded through)

MODERATE
  DATA_STEP, PROC_BLOCK, SQL_BLOCK
      → DEPENDENCY_PRESERVING  (intermediate complexity; keep lineage)
  MACRO_DEFINITION, MACRO_INVOCATION, CONDITIONAL_BLOCK, LOOP_BLOCK
      → MACRO_AWARE
  GLOBAL_STATEMENT, INCLUDE_REFERENCE
      → FLAT_PARTITION

HIGH (any type)
      → STRUCTURAL_GROUPING    (LLM with full context window + human review flag)

UNCERTAIN (any type)
      → HUMAN_REVIEW           (cannot auto-classify; escalate)
"""

from __future__ import annotations

from partition.base_agent import BaseAgent
from partition.models.enums import PartitionStrategy, PartitionType, RiskLevel
from partition.models.partition_ir import PartitionIR

# Types that need macro-aware handling
_MACRO_TYPES = {
    PartitionType.MACRO_DEFINITION,
    PartitionType.MACRO_INVOCATION,
    PartitionType.CONDITIONAL_BLOCK,
    PartitionType.LOOP_BLOCK,
}

# Types where data lineage must be preserved
_LINEAGE_TYPES = {
    PartitionType.DATA_STEP,
    PartitionType.PROC_BLOCK,
    PartitionType.SQL_BLOCK,
}

# Types safe for flat template translation
_FLAT_TYPES = {
    PartitionType.GLOBAL_STATEMENT,
    PartitionType.INCLUDE_REFERENCE,
}


def _select_strategy(risk: RiskLevel, ptype: PartitionType) -> PartitionStrategy:
    """Choose a ``PartitionStrategy`` for one block.

    Args:
        risk:  The block's assessed ``RiskLevel``.
        ptype: The SAS block type.

    Returns:
        The appropriate ``PartitionStrategy``.
    """
    if risk == RiskLevel.UNCERTAIN:
        return PartitionStrategy.HUMAN_REVIEW

    if risk == RiskLevel.HIGH:
        return PartitionStrategy.STRUCTURAL_GROUPING

    # LOW or MODERATE
    if ptype in _MACRO_TYPES:
        return PartitionStrategy.MACRO_AWARE

    if ptype == PartitionType.SQL_BLOCK:
        return PartitionStrategy.DEPENDENCY_PRESERVING

    if ptype in _LINEAGE_TYPES:
        if risk == RiskLevel.MODERATE:
            return PartitionStrategy.DEPENDENCY_PRESERVING
        # LOW lineage block → flat is sufficient
        return PartitionStrategy.FLAT_PARTITION

    # GLOBAL_STATEMENT, INCLUDE_REFERENCE → always flat
    return PartitionStrategy.FLAT_PARTITION


class StrategyAgent(BaseAgent):
    """Assign a ``PartitionStrategy`` to every block based on its ``RiskLevel``.

    Requires that ``ComplexityAgent.process()`` has already run (so that
    each block's ``risk_level`` is set).

    The selected strategy is stored in ``partition.metadata["strategy"]``
    for downstream agents (TranslationAgent, ValidationAgent).
    """

    agent_name = "StrategyAgent"

    async def process(  # type: ignore[override]
        self,
        partitions: list[PartitionIR],
    ) -> list[PartitionIR]:
        """Assign ``metadata["strategy"]`` to every block.

        Args:
            partitions: PartitionIR list with ``risk_level`` already set
                        by ``ComplexityAgent``.

        Returns:
            Updated list with ``metadata["strategy"]`` populated.
        """
        results: list[PartitionIR] = []
        strategy_counts: dict[str, int] = {}

        for part in partitions:
            strat = _select_strategy(part.risk_level, part.partition_type)
            key = strat.value
            strategy_counts[key] = strategy_counts.get(key, 0) + 1

            updated_meta = dict(part.metadata)
            updated_meta["strategy"] = key

            results.append(part.model_copy(update={"metadata": updated_meta}))

        self.logger.info(
            "strategies_assigned",
            n_blocks=len(results),
            distribution=strategy_counts,
        )
        return results
