"""RiskRouter — Consolidated L2-D agent.

Merges ComplexityAgent + StrategyAgent into a single agent:
score risk → assign strategy in one ``process()`` call.
"""

from __future__ import annotations

from partition.base_agent import BaseAgent
from partition.models.partition_ir import PartitionIR

from .complexity_agent import ComplexityAgent
from .strategy_agent import StrategyAgent, _select_strategy


class RiskRouter(BaseAgent):
    """Consolidated risk agent: complexity scoring + strategy assignment."""

    agent_name = "RiskRouter"

    def __init__(self) -> None:
        super().__init__()
        self._complexity = ComplexityAgent()
        self._strategy = StrategyAgent()

    def fit(self, *args, **kwargs):
        """Delegate to ComplexityAgent.fit()."""
        return self._complexity.fit(*args, **kwargs)

    async def process(  # type: ignore[override]
        self,
        partitions: list[PartitionIR],
    ) -> list[PartitionIR]:
        """Score complexity and assign strategies in one pass.

        Args:
            partitions: PartitionIR blocks from ChunkingAgent.

        Returns:
            Updated blocks with risk_level and metadata["strategy"] populated.
        """
        scored = await self._complexity.process(partitions)
        routed = await self._strategy.process(scored)
        return routed
