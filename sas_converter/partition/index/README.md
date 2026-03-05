# L2-E Index Layer (DAG & SCC Detection)

NetworkX-based dependency graph with Tarjan SCC detection, graph condensation, and dynamic hop cap.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 14 | `IndexAgent` | `index_agent.py` | Build DAG → detect SCCs → condense → compute hop cap |

## Files

| File | Description |
|------|-------------|
| `graph_builder.py` | `NetworkXGraphBuilder` — Persistent `nx.DiGraph` serialised to `.gpickle`; nodes carry partition metadata; edges carry `DEPENDS_ON` / `MACRO_CALLS` types |
| `index_agent.py` | Agent orchestration: build graph → Tarjan SCC → condense → dynamic hop cap (max 10) |

## Architecture

```
list[PartitionIR] + cross_file_deps (from Persistence + Entry)
        |
        v
  IndexAgent (#14)
    -> NetworkXGraphBuilder.add_partitions()
       Nodes = partitions with block_id, file_id, type
    -> NetworkXGraphBuilder.add_edges()
       Edges = DEPENDS_ON (data flow) + MACRO_CALLS (macro invocation)
        |
        v
  Tarjan SCC Detection (nx.strongly_connected_components)
    -> Identifies circular dependency groups
        |
        v
  Graph Condensation (nx.condensation)
    -> Collapses SCCs into super-nodes
    -> Result is a DAG (guaranteed acyclic)
        |
        v
  Dynamic Hop Cap
    -> max_hops = min(max_scc_size + 2, 10)
    -> Limits multi-hop traversal depth
        |
        v
  Output: {dag: DiGraph, sccs: list, condensed: DiGraph, hop_cap: int}
```

## Key Features

- **Persistent graph** — Serialised via `pickle` to `.gpickle` file
- **Tarjan SCC detection** — Finds circular dependencies in O(V+E)
- **Graph condensation** — Collapses cycles into super-nodes for guaranteed DAG
- **Dynamic hop cap** — Scales traversal depth with graph complexity (max 10)
- **Edge typing** — `DEPENDS_ON` (data flow) vs `MACRO_CALLS` (invocation)

## Dependencies

`networkx`, `pickle`, `structlog`
