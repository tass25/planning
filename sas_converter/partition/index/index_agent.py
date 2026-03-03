"""IndexAgent (#11) — DAG builder, SCC detection, and dynamic hop-cap."""

from __future__ import annotations

from typing import Optional

import networkx as nx
import structlog

from partition.base_agent import BaseAgent

logger = structlog.get_logger()


class IndexAgent(BaseAgent):
    """Agent #11 — Build dependency DAG, detect SCCs, compute hop cap.

    Three stages:
        1. Build a directed graph from partition dependency_refs.
        2. Detect Strongly Connected Components (circular deps).
        3. Condense the graph (collapse SCCs) and compute a dynamic hop cap.
    """

    agent_name = "IndexAgent"

    MAX_HOP_CAP = 10  # Upper bound for the hop cap

    async def process(
        self,
        partitions: list,
        cross_file_deps: Optional[dict[str, str]] = None,
    ) -> dict:
        """Run the full index pipeline.

        Args:
            partitions:     All PartitionIR-like objects.
            cross_file_deps: Mapping {ref_name → target_file_id} for cross-file edges.

        Returns:
            {
                "dag": nx.DiGraph,
                "sccs": list[set[str]],
                "condensed": nx.DiGraph,
                "hop_cap": int,
            }
        """
        cross_file_deps = cross_file_deps or {}

        dag = self._build_dag(partitions, cross_file_deps)
        sccs = self._detect_scc(dag)
        self._annotate_scc(partitions, sccs)
        condensed = self._condense(dag, sccs)
        hop_cap = self._compute_hop_cap(condensed)

        self.logger.info(
            "index_complete",
            nodes=dag.number_of_nodes(),
            edges=dag.number_of_edges(),
            sccs=len(sccs),
            hop_cap=hop_cap,
        )

        return {
            "dag": dag,
            "sccs": sccs,
            "condensed": condensed,
            "hop_cap": hop_cap,
        }

    # ------------------------------------------------------------------
    # Stage 1: Build DAG
    # ------------------------------------------------------------------

    def _build_dag(
        self,
        partitions: list,
        cross_file_deps: dict[str, str],
    ) -> nx.DiGraph:
        """Build a directed graph from partition dependencies."""
        dag = nx.DiGraph()
        partition_lookup: dict[str, object] = {}

        # Add all partition nodes
        for p in partitions:
            pid = str(getattr(p, 'partition_id', None) or getattr(p, 'block_id', ''))
            dag.add_node(
                pid,
                partition_type=getattr(p.partition_type, 'value', str(p.partition_type)),
                risk_level=getattr(p.risk_level, 'value', str(getattr(p, 'risk_level', ''))),
                complexity_score=getattr(p, 'complexity_score', 0.0),
                file_id=str(getattr(p, 'source_file_id', None) or getattr(p, 'file_id', '')),
            )
            partition_lookup[pid] = p

            # Index by produced datasets
            var_scope = getattr(p, 'variable_scope', None)
            if isinstance(var_scope, dict):
                for var_name in var_scope.get('outputs', []):
                    partition_lookup[f"dataset:{var_name.upper()}"] = p

        # Add edges
        for p in partitions:
            pid = str(getattr(p, 'partition_id', None) or getattr(p, 'block_id', ''))
            dep_refs = getattr(p, 'dependency_refs', [])

            for ref in dep_refs:
                ref_upper = ref.upper()

                # Dataset dependency
                producer_key = f"dataset:{ref_upper}"
                if producer_key in partition_lookup:
                    producer = partition_lookup[producer_key]
                    producer_pid = str(
                        getattr(producer, 'partition_id', None)
                        or getattr(producer, 'block_id', '')
                    )
                    if producer_pid != pid:
                        dag.add_edge(pid, producer_pid, dep_type="dataset", ref_raw=ref)

                # Cross-file dependency
                if ref in cross_file_deps:
                    target_file = cross_file_deps[ref]
                    for op in partitions:
                        op_fid = str(
                            getattr(op, 'source_file_id', None)
                            or getattr(op, 'file_id', '')
                        )
                        if op_fid == target_file:
                            op_pid = str(
                                getattr(op, 'partition_id', None)
                                or getattr(op, 'block_id', '')
                            )
                            dag.add_edge(pid, op_pid, dep_type="cross_file", ref_raw=ref)
                            break

            # Macro call edges
            macro_scope = getattr(p, 'macro_scope', None)
            if isinstance(macro_scope, dict):
                for macro_name in macro_scope.get('calls', []):
                    for op in partitions:
                        op_macro = getattr(op, 'macro_scope', None)
                        if (
                            isinstance(op_macro, dict)
                            and macro_name in op_macro.get('definitions', [])
                        ):
                            op_pid = str(
                                getattr(op, 'partition_id', None)
                                or getattr(op, 'block_id', '')
                            )
                            dag.add_edge(
                                pid, op_pid,
                                dep_type="macro_call",
                                macro_name=macro_name,
                            )
                            break

        self.logger.info(
            "dag_built",
            nodes=dag.number_of_nodes(),
            edges=dag.number_of_edges(),
        )
        return dag

    # ------------------------------------------------------------------
    # Stage 2: SCC detection
    # ------------------------------------------------------------------

    def _detect_scc(self, dag: nx.DiGraph) -> list[set]:
        """Find all Strongly Connected Components with size > 1 (cycles)."""
        all_sccs = list(nx.strongly_connected_components(dag))
        cycle_sccs = [scc for scc in all_sccs if len(scc) > 1]

        for i, scc in enumerate(cycle_sccs):
            self.logger.warning(
                "scc_detected",
                scc_id=i,
                size=len(scc),
                members=list(scc)[:5],
            )
        return cycle_sccs

    def _condense(self, dag: nx.DiGraph, scc_groups: list[set]) -> nx.DiGraph:
        """Collapse SCCs into super-nodes → guaranteed acyclic."""
        if not scc_groups:
            return dag
        condensed = nx.condensation(dag)
        self.logger.info(
            "dag_condensed",
            original_nodes=dag.number_of_nodes(),
            condensed_nodes=condensed.number_of_nodes(),
        )
        return condensed

    # ------------------------------------------------------------------
    # Stage 3: Dynamic hop cap
    # ------------------------------------------------------------------

    def _compute_hop_cap(self, condensed_dag: nx.DiGraph) -> int:
        """Compute dynamic hop cap = longest path length, capped at MAX_HOP_CAP."""
        try:
            if condensed_dag.number_of_nodes() == 0:
                return 1
            longest = nx.dag_longest_path_length(condensed_dag)
            hop_cap = min(longest, self.MAX_HOP_CAP)
        except nx.NetworkXUnfeasible:
            hop_cap = self.MAX_HOP_CAP
            self.logger.warning("hop_cap_fallback", reason="cycle_in_condensed")
        return hop_cap

    # ------------------------------------------------------------------
    # Annotation
    # ------------------------------------------------------------------

    def _annotate_scc(self, partitions: list, scc_groups: list[set]):
        """Set ``scc_id`` on partitions that belong to a cycle."""
        for scc_idx, scc in enumerate(scc_groups):
            scc_id = f"scc_{scc_idx}"
            for p in partitions:
                pid = str(getattr(p, 'partition_id', None) or getattr(p, 'block_id', ''))
                if pid in scc:
                    p.scc_id = scc_id
