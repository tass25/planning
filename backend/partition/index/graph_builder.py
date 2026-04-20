"""NetworkXGraphBuilder — persistent dependency graph with multi-hop traversal."""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path

import networkx as nx
import structlog

logger = structlog.get_logger()


class NetworkXGraphBuilder:
    """Build and persist a partition dependency graph in NetworkX.

    The graph is serialised to a pickle file so that it survives across
    pipeline invocations.  Nodes carry partition metadata; edges carry
    ``edge_type`` = DEPENDS_ON | MACRO_CALLS.
    """

    def __init__(self, persist_path: str = "partition_graph.gpickle"):
        self.persist_path = Path(persist_path)
        self.graph: nx.DiGraph = self._load_or_create()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def _hash_path(self) -> Path:
        return self.persist_path.with_suffix(".sha256")

    def _load_or_create(self) -> nx.DiGraph:
        """Load existing graph from pickle or create a new DiGraph.

        Verifies SHA-256 integrity before deserialising.
        """
        if self.persist_path.exists():
            try:
                raw = self.persist_path.read_bytes()
                # Integrity check: verify SHA-256 before unpickling
                if self._hash_path.exists():
                    expected = self._hash_path.read_text().strip()
                    actual = hashlib.sha256(raw).hexdigest()
                    if actual != expected:
                        logger.warning(
                            "graph_integrity_fail",
                            path=str(self.persist_path),
                            expected=expected[:12],
                            actual=actual[:12],
                        )
                        return nx.DiGraph()
                else:
                    logger.warning("graph_hash_missing", path=str(self._hash_path))

                g = pickle.loads(raw)  # noqa: S301 — integrity verified above
                logger.info("graph_loaded", path=str(self.persist_path), nodes=g.number_of_nodes())
                return g
            except Exception as exc:
                logger.warning("graph_load_failed", error=str(exc))
        return nx.DiGraph()

    def save(self):
        """Persist graph to pickle file with SHA-256 integrity hash."""
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        raw = pickle.dumps(self.graph)
        self.persist_path.write_bytes(raw)
        self._hash_path.write_text(hashlib.sha256(raw).hexdigest())

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_partitions(self, partitions: list) -> int:
        """Add partition nodes to the NetworkX graph."""
        added = 0
        for p in partitions:
            pid = str(getattr(p, "partition_id", None) or getattr(p, "block_id", ""))
            try:
                self.graph.add_node(
                    pid,
                    partition_type=getattr(p.partition_type, "value", str(p.partition_type)),
                    risk_level=getattr(p.risk_level, "value", str(getattr(p, "risk_level", ""))),
                    complexity_score=getattr(p, "complexity_score", 0.0),
                    file_id=str(getattr(p, "source_file_id", None) or getattr(p, "file_id", "")),
                    scc_id=getattr(p, "scc_id", None) or "",
                )
                added += 1
            except Exception as exc:
                logger.warning("graph_node_add_error", partition_id=pid, error=str(exc))
        self.save()
        return added

    def add_edges(self, dag: nx.DiGraph) -> int:
        """Copy edges from an IndexAgent DAG into the persistent graph."""
        added = 0
        for src, tgt, data in dag.edges(data=True):
            dep_type = data.get("dep_type", "dataset")
            try:
                if dep_type == "macro_call":
                    self.graph.add_edge(
                        src,
                        tgt,
                        edge_type="MACRO_CALLS",
                        macro_name=data.get("macro_name", ""),
                    )
                else:
                    self.graph.add_edge(
                        src,
                        tgt,
                        edge_type="DEPENDS_ON",
                        dep_type=dep_type,
                    )
                added += 1
            except Exception as exc:
                logger.warning("graph_edge_add_error", src=src, tgt=tgt, error=str(exc))
        self.save()
        return added

    # ------------------------------------------------------------------
    # Read / query
    # ------------------------------------------------------------------

    def query_dependencies(
        self,
        partition_id: str,
        max_hop: int = 3,
    ) -> list[dict]:
        """Multi-hop dependency traversal bounded by *max_hop* via BFS."""
        if partition_id not in self.graph:
            return []

        visited: set[str] = set()
        current_level = {partition_id}
        for _ in range(max_hop):
            next_level: set[str] = set()
            for node in current_level:
                for succ in self.graph.successors(node):
                    if succ not in visited and succ != partition_id:
                        visited.add(succ)
                        next_level.add(succ)
            current_level = next_level
            if not current_level:
                break

        rows: list[dict] = []
        for nid in visited:
            attrs = self.graph.nodes[nid]
            rows.append(
                {
                    "partition_id": nid,
                    "partition_type": attrs.get("partition_type", ""),
                    "risk_level": attrs.get("risk_level", ""),
                    "scc_id": attrs.get("scc_id", ""),
                }
            )
        return rows

    def query_scc_members(self, scc_id: str) -> list[str]:
        """Get all partition IDs in a given SCC group."""
        return [nid for nid, attrs in self.graph.nodes(data=True) if attrs.get("scc_id") == scc_id]

    def count_nodes(self) -> int:
        return self.graph.number_of_nodes()

    def count_edges(self) -> int:
        return self.graph.number_of_edges()
