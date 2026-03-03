# Week 7 — Done: Persistence & Index Layer (L3)

> **Commit**: `1fcba49` on `main`
> **Tests**: 115/115 passing (24 new + 91 existing)
> **Layer**: L3 — Persistence, Indexing, Analytics

---

## Summary

Implemented the full Persistence & Index layer as specified in `week-07.md`.
PersistenceAgent writes PartitionIR objects to SQLite with content-hash dedup.
IndexAgent builds the dependency DAG, detects SCCs, condenses cycles, and computes a dynamic hop cap.
NetworkXGraphBuilder provides persistent multi-hop traversal.
DuckDB analytics schema initialises 7 tables for LLM audit, calibration, ablation, quality metrics, and more.
ProjectConfigManager persists dynamic hop cap and pipeline config to YAML.

---

## Deliverables

### 1. PersistenceAgent (#10) — `partition/persistence/persistence_agent.py`

| Feature | Status |
|---------|--------|
| Extends BaseAgent with `agent_name = "PersistenceAgent"` | ✅ |
| SHA-256 content-hash dedup (skips duplicate raw_code) | ✅ |
| Auto-creates FileRegistryRow stubs for FK satisfaction | ✅ |
| Batch write via SQLAlchemy Session | ✅ |
| Parquet fallback stub for batches ≥ 10,000 | ✅ |
| Accepts `db_url` (full SQLAlchemy URL) or plain path | ✅ |

### 2. IndexAgent (#11) — `partition/index/index_agent.py`

| Feature | Status |
|---------|--------|
| `_build_dag()` — DiGraph from dependency_refs, variable_scope outputs, macro_scope calls, cross-file deps | ✅ |
| `_detect_scc()` — SCCs with size > 1 (circular dependencies) | ✅ |
| `_condense()` — SCC collapse via `nx.condensation()` → guaranteed acyclic | ✅ |
| `_compute_hop_cap()` — `min(dag_longest_path_length, 10)` | ✅ |
| `_annotate_scc()` — sets `scc_id` on partition objects | ✅ |

### 3. NetworkXGraphBuilder — `partition/index/graph_builder.py`

| Feature | Status |
|---------|--------|
| `add_partitions()` — nodes with metadata | ✅ |
| `add_edges()` — edges with DEPENDS_ON / MACRO_CALLS types | ✅ |
| `query_dependencies(pid, max_hop)` — BFS bounded traversal | ✅ |
| `query_scc_members(scc_id)` — list all members of an SCC | ✅ |
| Pickle persistence (auto-save/load) | ✅ |

### 4. DuckDB Analytics — `partition/db/duckdb_manager.py`

| Table | Purpose |
|-------|---------|
| `llm_audit` | LLM call tracing (model, latency, success) |
| `calibration_log` | Complexity calibration history |
| `ablation_results` | Feature ablation experiments |
| `quality_metrics` | Code quality scores |
| `feedback_log` | Human review feedback |
| `kb_changelog` | Knowledge base change tracking |
| `conversion_reports` | End-to-end conversion reports |

Helper: `log_llm_call()` for audit insertion.

### 5. ProjectConfigManager — `partition/config/config_manager.py`

| Feature | Status |
|---------|--------|
| `set_max_hop(int)` / `get_max_hop()` → stored in `graph.max_hop` | ✅ |
| Generic `set(key, value)` / `get(key, default)` accessors | ✅ |
| Auto-creates directories, auto-saves on every `set()` | ✅ |
| YAML persistence (round-trip safe) | ✅ |

### 6. SQLite Schema Extensions — `partition/db/sqlite_manager.py`

3 new ORM models added:

- **PartitionIRRow** — partition_id, source_file_id (FK→file_registry), partition_type, risk_level, content_hash, complexity_score, calibration_confidence, strategy, line range, control_depth, has_macros, has_nested_sql, raw_code, RAPTOR back-links, scc_id
- **ConversionResultRow** — conversion_id, partition_id (FK→partition_ir), target_lang, translated_code, validation_status, error_log, llm_model/tier, retry_count
- **MergedScriptRow** — script_id, source_file_id (FK→file_registry), output_path, n_blocks, status

---

## Test Coverage — `tests/test_persistence.py` (24 tests)

| Test Class | Tests | All Pass |
|------------|-------|----------|
| `TestPersistenceAgent` | 5 (sql_write, sql_dedup, table_creation, empty_partitions, pipeline_twice_same_count) | ✅ |
| `TestIndexAgent` | 8 (scc_detection, no_scc_in_dag, hop_cap, hop_cap_max, condense_removes_cycles, annotate_scc, build_dag_with_deps, full_process) | ✅ |
| `TestNetworkXGraphBuilder` | 5 (add_partitions, add_edges, multi_hop_traversal, persistence, scc_members_query) | ✅ |
| `TestDuckDB` | 2 (all_tables_created, llm_audit_insert) | ✅ |
| `TestProjectConfigManager` | 4 (set_and_get_max_hop, default_hop, persistence, generic_set_get) | ✅ |

**Full pipeline coherence**: 115/115 tests pass (all weeks 1–7).

---

## Dependencies Added — `requirements.txt`

```
networkx>=3.1
duckdb>=0.9
pyyaml>=6.0
```

---

## Files Created / Modified

| File | Action |
|------|--------|
| `partition/persistence/__init__.py` | Created |
| `partition/persistence/persistence_agent.py` | Created |
| `partition/index/__init__.py` | Created |
| `partition/index/index_agent.py` | Created |
| `partition/index/graph_builder.py` | Created |
| `partition/db/duckdb_manager.py` | Created |
| `partition/config/__init__.py` | Created |
| `partition/config/config_manager.py` | Created |
| `partition/db/sqlite_manager.py` | Modified (+3 ORM models) |
| `requirements.txt` | Modified (+3 deps) |
| `tests/test_persistence.py` | Created (24 tests) |

---

## Architecture After Week 7

```
PartitionIR[] + RAPTORNode[]
        │
        ├─── PersistenceAgent ──▶ SQLite (partition_ir, conversion_results, merged_scripts)
        │                    └──▶ Parquet (batches ≥ 10,000)
        │
        ├─── RAPTORWriter ──▶ LanceDB raptor_nodes (Week 5-6)
        │
        └─── IndexAgent ──▶ Stage 1: NetworkX DAG
                        └──▶ Stage 2: SCC Condensation (nx.condensation)
                        └──▶ Stage 3: Dynamic Hop Cap (min(longest_path, 10))

        NetworkXGraphBuilder ──▶ Persistent graph (.gpickle)
        DuckDB ──▶ 7 analytics tables
        ProjectConfigManager ──▶ YAML config (hop cap, pipeline settings)
```
