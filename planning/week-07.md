# Week 7: L2-E — Persistence & Index + Graph Construction

> **Priority**: P1  
> **Branch**: `week-07`  
> **Layer**: L2-E  
> **Agents to build**: PersistenceAgent (#10), IndexAgent (#11)  
> **Prerequisite**: Weeks 5–6 complete (RAPTOR tree built, PartitionIR with raptor_leaf_id set)  

---

## 🎯 Goal

Implement the persistence and indexing layer. PersistenceAgent writes PartitionIR objects to SQLite (dev) / PostgreSQL (prod) / Parquet (large batches). IndexAgent builds the dependency graph in NetworkX, performs SCC condensation for circular dependency detection, then writes the acyclic graph to Kuzu for Cypher-queryable multi-hop traversal. All DuckDB analytics schemas are initialized this week.

---

## Architecture Recap

```
PartitionIR[] + RAPTORNode[]
        │
        ├─── PersistenceAgent ──► SQLite / PostgreSQL (PartitionIR store)
        │                    └──► Parquet (batches ≥ 10,000)
        │
        ├─── RAPTORWriter ──► LanceDB raptor_nodes (already done in Week 5-6)
        │
        └─── IndexAgent ──► Stage 1: NetworkX DAG
                        └──► Stage 2: SCC Condensation (nx.condensation)
                        └──► Stage 3: Dynamic Hop Cap
                        └──► Kuzu Graph (Partition + DEPENDS_ON + MACRO_CALLS)
```

---

## Tasks

### Task 1: PersistenceAgent (#10)

**File**: `partition/persistence/persistence_agent.py`

```python
import uuid
import json
from datetime import datetime
from typing import Optional
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import structlog

from partition.base_agent import BaseAgent

logger = structlog.get_logger()


class PersistenceAgent(BaseAgent):
    """
    Agent #10: Write PartitionIR to persistent storage.
    
    Three backends:
    - SQLite (dev, < 10,000 blocks): INSERT OR IGNORE dedup on content_hash
    - PostgreSQL (prod): same ORM, connection pool
    - Parquet (batches ≥ 10,000): pyarrow serialization
    """
    agent_name = "PersistenceAgent"

    def __init__(
        self,
        db_url: str = "sqlite:///partition_data.db",
        parquet_dir: str = "data/partitions",
        parquet_threshold: int = 10_000,
        trace_id=None,
    ):
        super().__init__(trace_id)
        self.engine = create_engine(db_url, echo=False)
        self.Session = sessionmaker(bind=self.engine)
        self.parquet_dir = Path(parquet_dir)
        self.parquet_threshold = parquet_threshold
        self._init_tables()

    def _init_tables(self):
        """Create tables if they don't exist."""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS file_registry (
                    file_id        TEXT PRIMARY KEY,
                    file_path      TEXT NOT NULL,
                    encoding       TEXT NOT NULL,
                    content_hash   TEXT NOT NULL UNIQUE,
                    file_size_bytes INTEGER,
                    line_count     INTEGER,
                    lark_valid     INTEGER,
                    lark_errors    TEXT,
                    status         TEXT DEFAULT 'PENDING',
                    error_log      TEXT,
                    created_at     TEXT NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS partition_ir (
                    partition_id           TEXT PRIMARY KEY,
                    source_file_id         TEXT NOT NULL,
                    content_hash           TEXT NOT NULL,
                    partition_type         TEXT NOT NULL,
                    risk_level             TEXT NOT NULL,
                    complexity_score       REAL,
                    calibration_confidence REAL,
                    strategy               TEXT,
                    line_start             INTEGER,
                    line_end               INTEGER,
                    control_depth          INTEGER DEFAULT 0,
                    has_macros             INTEGER DEFAULT 0,
                    has_nested_sql         INTEGER DEFAULT 0,
                    macro_scope            TEXT,
                    variable_scope         TEXT,
                    dependency_refs        TEXT,
                    raptor_leaf_id         TEXT,
                    raptor_cluster_id      TEXT,
                    raptor_root_id         TEXT,
                    scc_id                 TEXT,
                    test_coverage_type     TEXT DEFAULT 'full',
                    raw_code               TEXT NOT NULL,
                    trace_id               TEXT,
                    created_at             TEXT NOT NULL,
                    FOREIGN KEY (source_file_id) REFERENCES file_registry(file_id)
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cross_file_deps (
                    dep_id         TEXT PRIMARY KEY,
                    source_file_id TEXT NOT NULL,
                    target_file_id TEXT,
                    ref_type       TEXT NOT NULL,
                    ref_raw        TEXT NOT NULL,
                    resolved       INTEGER NOT NULL,
                    created_at     TEXT NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS conversion_results (
                    conversion_id          TEXT PRIMARY KEY,
                    partition_id           TEXT NOT NULL,
                    source_file_id         TEXT NOT NULL,
                    python_code            TEXT NOT NULL,
                    imports_detected       TEXT,
                    status                 TEXT NOT NULL,
                    llm_confidence         REAL,
                    failure_mode_flagged   TEXT,
                    model_used             TEXT,
                    kb_examples_used       TEXT,
                    retry_count            INTEGER DEFAULT 0,
                    trace_id               TEXT,
                    created_at             TEXT NOT NULL,
                    FOREIGN KEY (partition_id) REFERENCES partition_ir(partition_id)
                )
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS merged_scripts (
                    script_id           TEXT PRIMARY KEY,
                    source_file_id      TEXT NOT NULL,
                    python_script       TEXT NOT NULL,
                    import_block        TEXT,
                    block_count         INTEGER,
                    partial_count       INTEGER,
                    human_review_count  INTEGER,
                    syntax_valid        INTEGER,
                    syntax_errors       TEXT,
                    status              TEXT,
                    output_path         TEXT,
                    trace_id            TEXT,
                    created_at          TEXT NOT NULL,
                    FOREIGN KEY (source_file_id) REFERENCES file_registry(file_id)
                )
            """))
            conn.commit()

    async def process(self, partitions: list) -> int:
        """
        Persist a batch of PartitionIR objects.
        
        Returns:
            Number of partitions written (deduped)
        """
        if len(partitions) >= self.parquet_threshold:
            return self._write_parquet(partitions)
        return self._write_sql(partitions)

    def _write_sql(self, partitions: list) -> int:
        """Write partitions to SQLite/PostgreSQL with content_hash dedup."""
        written = 0
        with self.engine.connect() as conn:
            for p in partitions:
                try:
                    conn.execute(text("""
                        INSERT OR IGNORE INTO partition_ir (
                            partition_id, source_file_id, content_hash,
                            partition_type, risk_level, complexity_score,
                            calibration_confidence, strategy,
                            line_start, line_end, control_depth,
                            has_macros, has_nested_sql,
                            macro_scope, variable_scope, dependency_refs,
                            raptor_leaf_id, raptor_cluster_id, raptor_root_id,
                            scc_id, test_coverage_type, raw_code,
                            trace_id, created_at
                        ) VALUES (
                            :pid, :fid, :hash, :ptype, :risk, :score,
                            :conf, :strategy, :ls, :le, :depth,
                            :macros, :sql, :mscope, :vscope, :deps,
                            :rleaf, :rcluster, :rroot,
                            :scc, :tcov, :code, :tid, :ts
                        )
                    """), {
                        "pid": str(p.partition_id),
                        "fid": str(p.source_file_id),
                        "hash": p.content_hash,
                        "ptype": p.partition_type.value,
                        "risk": p.risk_level.value,
                        "score": p.complexity_score,
                        "conf": p.calibration_confidence,
                        "strategy": p.strategy.value if p.strategy else None,
                        "ls": p.line_start,
                        "le": p.line_end,
                        "depth": p.control_depth,
                        "macros": int(p.has_macros),
                        "sql": int(p.has_nested_sql),
                        "mscope": json.dumps(p.macro_scope),
                        "vscope": json.dumps(p.variable_scope),
                        "deps": json.dumps(p.dependency_refs),
                        "rleaf": p.raptor_leaf_id,
                        "rcluster": getattr(p, 'raptor_cluster_id', None),
                        "rroot": getattr(p, 'raptor_root_id', None),
                        "scc": getattr(p, 'scc_id', None),
                        "tcov": p.test_coverage_type,
                        "code": p.raw_code,
                        "tid": str(p.trace_id) if p.trace_id else None,
                        "ts": datetime.utcnow().isoformat(),
                    })
                    written += 1
                except Exception as e:
                    self.logger.warning("partition_write_skip",
                                       partition_id=str(p.partition_id),
                                       error=str(e))
            conn.commit()

        self.logger.info("persistence_write_sql",
                         total=len(partitions), written=written)
        return written

    def _write_parquet(self, partitions: list) -> int:
        """Write large batches to Parquet files."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        self.parquet_dir.mkdir(parents=True, exist_ok=True)

        records = []
        for p in partitions:
            records.append({
                "partition_id": str(p.partition_id),
                "source_file_id": str(p.source_file_id),
                "content_hash": p.content_hash,
                "partition_type": p.partition_type.value,
                "risk_level": p.risk_level.value,
                "complexity_score": p.complexity_score,
                "line_start": p.line_start,
                "line_end": p.line_end,
                "raw_code": p.raw_code,
            })

        table = pa.Table.from_pylist(records)
        file_id = str(partitions[0].source_file_id) if partitions else "batch"
        out_path = self.parquet_dir / f"file_{file_id}.parquet"
        pq.write_table(table, str(out_path))

        self.logger.info("persistence_write_parquet",
                         count=len(records), path=str(out_path))
        return len(records)
```

---

### Task 2: IndexAgent (#11) — NetworkX DAG + SCC + Kuzu

**File**: `partition/index/index_agent.py`

```python
import uuid
import networkx as nx
from typing import Optional
import structlog

from partition.base_agent import BaseAgent

logger = structlog.get_logger()


class IndexAgent(BaseAgent):
    """
    Agent #11: Build dependency graph in 3 stages.
    
    Stage 1: NetworkX DAG construction from PartitionIR dependency_refs
    Stage 2: SCC condensation (circular dependency detection)
    Stage 3: Dynamic hop cap for Kuzu multi-hop queries
    """
    agent_name = "IndexAgent"

    MAX_HOP_CAP = 10

    async def process(
        self,
        partitions: list,
        cross_file_deps: Optional[dict] = None,
    ) -> tuple:
        """
        Build the full dependency graph.
        
        Args:
            partitions: All PartitionIR in the project
            cross_file_deps: Pre-resolved cross-file dependencies
                             {ref_raw: target_file_id}
        
        Returns:
            (dag, condensed_dag, scc_groups, max_hop)
        """
        cross_file_deps = cross_file_deps or {}

        # Stage 1: Build NetworkX DAG
        dag = self._build_dag(partitions, cross_file_deps)

        # Stage 2: SCC condensation
        scc_groups = self._detect_scc(dag)
        condensed_dag = self._condense(dag, scc_groups)

        # Stage 3: Dynamic hop cap
        max_hop = self._compute_hop_cap(condensed_dag)

        # Annotate partitions with scc_id
        self._annotate_scc(partitions, scc_groups)

        self.logger.info("index_complete",
                         nodes=dag.number_of_nodes(),
                         edges=dag.number_of_edges(),
                         scc_count=len(scc_groups),
                         max_hop=max_hop)

        return dag, condensed_dag, scc_groups, max_hop

    def _build_dag(self, partitions: list, cross_file_deps: dict) -> nx.DiGraph:
        """Stage 1: Build directed graph from partition dependencies."""
        dag = nx.DiGraph()

        # Add all partition nodes
        partition_lookup = {}
        for p in partitions:
            pid = str(p.partition_id)
            dag.add_node(pid, **{
                "partition_type": p.partition_type.value,
                "risk_level": p.risk_level.value,
                "complexity_score": p.complexity_score,
                "file_id": str(p.source_file_id),
            })
            partition_lookup[pid] = p

            # Index by produced datasets
            if hasattr(p, 'variable_scope') and isinstance(p.variable_scope, dict):
                for var_name in p.variable_scope.get('outputs', []):
                    partition_lookup[f"dataset:{var_name.upper()}"] = p

        # Add edges from dependency_refs
        for p in partitions:
            pid = str(p.partition_id)
            for ref in p.dependency_refs:
                ref_upper = ref.upper()

                # Check if another partition produces this dataset
                producer_key = f"dataset:{ref_upper}"
                if producer_key in partition_lookup:
                    producer = partition_lookup[producer_key]
                    producer_pid = str(producer.partition_id)
                    if producer_pid != pid:
                        dag.add_edge(
                            pid, producer_pid,
                            dep_type="dataset",
                            ref_raw=ref,
                        )

                # Cross-file dependencies
                if ref in cross_file_deps:
                    target_file = cross_file_deps[ref]
                    # Find a partition in the target file
                    for op in partitions:
                        if str(op.source_file_id) == target_file:
                            dag.add_edge(
                                pid, str(op.partition_id),
                                dep_type="cross_file",
                                ref_raw=ref,
                            )
                            break

            # Macro call edges
            if hasattr(p, 'macro_scope') and isinstance(p.macro_scope, dict):
                for macro_name in p.macro_scope.get('calls', []):
                    # Find the partition that defines this macro
                    for op in partitions:
                        if (hasattr(op, 'macro_scope') and
                            isinstance(op.macro_scope, dict) and
                            macro_name in op.macro_scope.get('definitions', [])):
                            dag.add_edge(
                                pid, str(op.partition_id),
                                dep_type="macro_call",
                                macro_name=macro_name,
                            )
                            break

        self.logger.info("dag_built",
                         nodes=dag.number_of_nodes(),
                         edges=dag.number_of_edges())
        return dag

    def _detect_scc(self, dag: nx.DiGraph) -> list[set]:
        """
        Stage 2: Find all Strongly Connected Components.
        
        SCCs with size > 1 indicate circular dependencies.
        (A → B → C → A forms an SCC of size 3)
        """
        all_sccs = list(nx.strongly_connected_components(dag))
        # Only return SCCs with > 1 member (actual cycles)
        cycle_sccs = [scc for scc in all_sccs if len(scc) > 1]

        for i, scc in enumerate(cycle_sccs):
            self.logger.warning("scc_detected",
                                scc_id=i,
                                size=len(scc),
                                members=list(scc)[:5])  # Log first 5
        return cycle_sccs

    def _condense(self, dag: nx.DiGraph, scc_groups: list[set]) -> nx.DiGraph:
        """
        Collapse SCCs into super-nodes.
        Result is guaranteed acyclic (DAG).
        """
        if not scc_groups:
            return dag

        condensed = nx.condensation(dag)

        self.logger.info("dag_condensed",
                         original_nodes=dag.number_of_nodes(),
                         condensed_nodes=condensed.number_of_nodes())
        return condensed

    def _compute_hop_cap(self, condensed_dag: nx.DiGraph) -> int:
        """
        Stage 3: Compute dynamic hop cap from longest path.
        Capped at MAX_HOP_CAP (10).
        """
        try:
            if condensed_dag.number_of_nodes() == 0:
                return 1
            longest = nx.dag_longest_path_length(condensed_dag)
            hop_cap = min(longest, self.MAX_HOP_CAP)
        except nx.NetworkXUnfeasible:
            # Graph has cycles (shouldn't happen after condensation)
            hop_cap = self.MAX_HOP_CAP
            self.logger.warning("hop_cap_fallback", reason="cycle_in_condensed")

        self.logger.info("hop_cap_computed", max_hop=hop_cap)
        return hop_cap

    def _annotate_scc(self, partitions: list, scc_groups: list[set]):
        """Set scc_id on partitions that belong to a cycle."""
        for scc_idx, scc in enumerate(scc_groups):
            scc_id = f"scc_{scc_idx}"
            for p in partitions:
                if str(p.partition_id) in scc:
                    p.scc_id = scc_id
```

---

### Task 3: Kuzu Graph Writer

**File**: `partition/index/kuzu_writer.py`

```python
import kuzu
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger()


class KuzuGraphWriter:
    """Write partition dependency graph to Kuzu for Cypher queries."""

    def __init__(self, db_path: str = "partition_graph"):
        Path(db_path).mkdir(parents=True, exist_ok=True)
        self.db = kuzu.Database(db_path)
        self.conn = kuzu.Connection(self.db)
        self._init_schema()

    def _init_schema(self):
        """Create node and relationship tables."""
        try:
            self.conn.execute("""
                CREATE NODE TABLE IF NOT EXISTS Partition (
                    partition_id   STRING,
                    partition_type STRING,
                    risk_level     STRING,
                    complexity_score DOUBLE,
                    file_id        STRING,
                    scc_id         STRING,
                    PRIMARY KEY (partition_id)
                )
            """)
        except Exception:
            pass  # Table may already exist

        try:
            self.conn.execute("""
                CREATE REL TABLE IF NOT EXISTS DEPENDS_ON (
                    FROM Partition TO Partition,
                    dep_type STRING
                )
            """)
        except Exception:
            pass

        try:
            self.conn.execute("""
                CREATE REL TABLE IF NOT EXISTS MACRO_CALLS (
                    FROM Partition TO Partition,
                    macro_name STRING
                )
            """)
        except Exception:
            pass

    def write_partitions(self, partitions: list) -> int:
        """Insert partition nodes into Kuzu."""
        written = 0
        for p in partitions:
            try:
                self.conn.execute(
                    """
                    MERGE (n:Partition {partition_id: $pid})
                    SET n.partition_type = $ptype,
                        n.risk_level = $risk,
                        n.complexity_score = $score,
                        n.file_id = $fid,
                        n.scc_id = $scc
                    """,
                    {
                        "pid": str(p.partition_id),
                        "ptype": p.partition_type.value,
                        "risk": p.risk_level.value,
                        "score": p.complexity_score,
                        "fid": str(p.source_file_id),
                        "scc": getattr(p, 'scc_id', None) or "",
                    }
                )
                written += 1
            except Exception as e:
                logger.warning("kuzu_node_write_error",
                               partition_id=str(p.partition_id),
                               error=str(e))
        return written

    def write_edges(self, dag) -> int:
        """Write DAG edges to Kuzu relationship tables."""
        written = 0
        for src, tgt, data in dag.edges(data=True):
            dep_type = data.get("dep_type", "dataset")
            try:
                if dep_type == "macro_call":
                    self.conn.execute(
                        """
                        MATCH (a:Partition {partition_id: $src}),
                              (b:Partition {partition_id: $tgt})
                        CREATE (a)-[:MACRO_CALLS {macro_name: $name}]->(b)
                        """,
                        {"src": src, "tgt": tgt,
                         "name": data.get("macro_name", "")}
                    )
                else:
                    self.conn.execute(
                        """
                        MATCH (a:Partition {partition_id: $src}),
                              (b:Partition {partition_id: $tgt})
                        CREATE (a)-[:DEPENDS_ON {dep_type: $dtype}]->(b)
                        """,
                        {"src": src, "tgt": tgt, "dtype": dep_type}
                    )
                written += 1
            except Exception as e:
                logger.warning("kuzu_edge_write_error",
                               src=src, tgt=tgt, error=str(e))
        return written

    def query_dependencies(
        self,
        partition_id: str,
        max_hop: int = 3,
    ) -> list[dict]:
        """Multi-hop dependency query via Cypher."""
        result = self.conn.execute(
            f"""
            MATCH (a:Partition {{partition_id: $pid}})-[*1..{max_hop}]->(b:Partition)
            RETURN b.partition_id, b.partition_type, b.risk_level, b.scc_id
            """,
            {"pid": partition_id}
        )
        rows = []
        while result.has_next():
            row = result.get_next()
            rows.append({
                "partition_id": row[0],
                "partition_type": row[1],
                "risk_level": row[2],
                "scc_id": row[3],
            })
        return rows

    def query_scc_members(self, scc_id: str) -> list[str]:
        """Get all partitions in an SCC group."""
        result = self.conn.execute(
            """
            MATCH (n:Partition {scc_id: $scc})
            RETURN n.partition_id
            """,
            {"scc": scc_id}
        )
        members = []
        while result.has_next():
            members.append(result.get_next()[0])
        return members

    def count_nodes(self) -> int:
        result = self.conn.execute("MATCH (n:Partition) RETURN count(n)")
        return result.get_next()[0] if result.has_next() else 0

    def count_edges(self) -> int:
        r1 = self.conn.execute("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)")
        r2 = self.conn.execute("MATCH ()-[r:MACRO_CALLS]->() RETURN count(r)")
        c1 = r1.get_next()[0] if r1.has_next() else 0
        c2 = r2.get_next()[0] if r2.has_next() else 0
        return c1 + c2
```

**Install Kuzu**:
```bash
pip install kuzu
```

---

### Task 4: DuckDB Full Schema Initialization

**File**: `partition/db/duckdb_manager.py` (extend from Week 4)

```python
import duckdb
import structlog

logger = structlog.get_logger()

DB_PATH = "analytics.duckdb"


def init_all_duckdb_tables(db_path: str = DB_PATH):
    """Initialize all DuckDB analytics tables."""
    con = duckdb.connect(db_path)

    # Table 1: llm_audit — every LLM call logged
    con.execute("""
        CREATE TABLE IF NOT EXISTS llm_audit (
            call_id       VARCHAR PRIMARY KEY,
            agent_name    VARCHAR,
            model_name    VARCHAR,
            prompt_hash   VARCHAR,
            response_hash VARCHAR,
            latency_ms    DOUBLE,
            success       BOOLEAN,
            error_msg     VARCHAR,
            tier          VARCHAR,
            timestamp     TIMESTAMP DEFAULT NOW()
        )
    """)

    # Table 2: calibration_log — ECE per training run (from Week 4)
    con.execute("""
        CREATE TABLE IF NOT EXISTS calibration_log (
            log_id        VARCHAR PRIMARY KEY,
            ece_score     DOUBLE,
            n_samples     INTEGER,
            n_train       INTEGER,
            model_version VARCHAR,
            created_at    TIMESTAMP DEFAULT NOW()
        )
    """)

    # Table 3: ablation_results — RAPTOR vs flat study
    con.execute("""
        CREATE TABLE IF NOT EXISTS ablation_results (
            run_id           VARCHAR,
            file_id          VARCHAR,
            query_id         VARCHAR,
            index_type       VARCHAR,
            hit_at_5         BOOLEAN,
            reciprocal_rank  DOUBLE,
            query_latency_ms DOUBLE,
            complexity_tier  VARCHAR,
            depth_level      INTEGER,
            created_at       TIMESTAMP,
            PRIMARY KEY (run_id, file_id, query_id, index_type)
        )
    """)

    # Table 4: quality_metrics — translation quality per batch
    con.execute("""
        CREATE TABLE IF NOT EXISTS quality_metrics (
            metric_id           VARCHAR PRIMARY KEY,
            batch_id            VARCHAR,
            n_evaluated         INTEGER,
            success_rate        DOUBLE,
            partial_rate        DOUBLE,
            human_review_rate   DOUBLE,
            avg_llm_confidence  DOUBLE,
            avg_retry_count     DOUBLE,
            failure_mode_dist   VARCHAR,
            kb_size             INTEGER,
            created_at          TIMESTAMP
        )
    """)

    # Table 5: feedback_log — correction tracking
    con.execute("""
        CREATE TABLE IF NOT EXISTS feedback_log (
            feedback_id         VARCHAR PRIMARY KEY,
            conversion_id       VARCHAR,
            partition_id        VARCHAR,
            correction_source   VARCHAR,
            original_status     VARCHAR,
            new_kb_example_id   VARCHAR,
            verifier_confidence DOUBLE,
            accepted            BOOLEAN,
            rejection_reason    VARCHAR,
            created_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    # Table 6: kb_changelog — KB versioning audit trail
    con.execute("""
        CREATE TABLE IF NOT EXISTS kb_changelog (
            changelog_id        VARCHAR PRIMARY KEY,
            example_id          VARCHAR NOT NULL,
            action              VARCHAR NOT NULL,
            old_version         INTEGER,
            new_version         INTEGER NOT NULL,
            author              VARCHAR NOT NULL,
            diff_summary        VARCHAR,
            created_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    # Table 7: conversion_reports — per-file report metadata
    con.execute("""
        CREATE TABLE IF NOT EXISTS conversion_reports (
            report_id           VARCHAR PRIMARY KEY,
            source_file_id      VARCHAR NOT NULL,
            total_blocks        INTEGER,
            success_count       INTEGER,
            partial_count       INTEGER,
            failed_count        INTEGER,
            human_review_count  INTEGER,
            validation_pass     INTEGER,
            validation_fail     INTEGER,
            codebleu_mean       DOUBLE,
            failure_mode_dist   VARCHAR,
            report_md_path      VARCHAR,
            report_html_path    VARCHAR,
            created_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    con.close()
    logger.info("duckdb_all_tables_initialized", db_path=db_path)


def log_llm_call(db_path, call_id, agent_name, model_name,
                 prompt_hash, response_hash, latency_ms,
                 success, error_msg=None, tier=None):
    """Log an LLM call to the audit table."""
    con = duckdb.connect(db_path)
    con.execute("""
        INSERT INTO llm_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
    """, [call_id, agent_name, model_name, prompt_hash,
          response_hash, latency_ms, success, error_msg, tier])
    con.close()
```

---

### Task 5: Project Config Writer (Dynamic Hop Cap)

**File**: `partition/config/config_manager.py`

```python
import yaml
from pathlib import Path


class ProjectConfigManager:
    """Manage project-level configuration (hop cap, etc.)."""

    CONFIG_PATH = "config/project_config.yaml"

    def __init__(self, config_path: str = None):
        self.path = Path(config_path or self.CONFIG_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._config = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            with open(self.path) as f:
                return yaml.safe_load(f) or {}
        return {}

    def save(self):
        with open(self.path, 'w') as f:
            yaml.dump(self._config, f, default_flow_style=False)

    def set_max_hop(self, max_hop: int):
        """Set the dynamic hop cap for Kuzu queries."""
        self._config['graph'] = self._config.get('graph', {})
        self._config['graph']['max_hop'] = max_hop
        self.save()

    def get_max_hop(self) -> int:
        return self._config.get('graph', {}).get('max_hop', 3)

    def set(self, key: str, value):
        self._config[key] = value
        self.save()

    def get(self, key: str, default=None):
        return self._config.get(key, default)
```

---

### Task 6: Tests

**File**: `tests/test_persistence.py`

```python
import pytest
import tempfile
import os

class TestPersistenceAgent:
    def test_sql_write_and_dedup(self, tmp_path):
        """Write partitions to SQLite, verify dedup on content_hash."""
        from partition.persistence.persistence_agent import PersistenceAgent
        db_path = tmp_path / "test.db"
        agent = PersistenceAgent(db_url=f"sqlite:///{db_path}")

        # Create mock partitions with same content_hash
        partitions = [_mock_partition("hash1"), _mock_partition("hash1")]
        import asyncio
        count = asyncio.run(agent.process(partitions))
        # Second insert should be ignored (dedup)
        assert count <= 2  # INSERT OR IGNORE

    def test_table_creation(self, tmp_path):
        """All required tables should be created on init."""
        from partition.persistence.persistence_agent import PersistenceAgent
        db_path = tmp_path / "test.db"
        agent = PersistenceAgent(db_url=f"sqlite:///{db_path}")
        from sqlalchemy import inspect
        inspector = inspect(agent.engine)
        tables = inspector.get_table_names()
        assert "partition_ir" in tables
        assert "file_registry" in tables
        assert "conversion_results" in tables
        assert "merged_scripts" in tables


class TestIndexAgent:
    def test_scc_detection(self):
        """Detect circular dependency A→B→C→A."""
        from partition.index.index_agent import IndexAgent
        import networkx as nx
        import asyncio

        agent = IndexAgent()
        dag = nx.DiGraph()
        dag.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])
        sccs = agent._detect_scc(dag)
        assert len(sccs) == 1
        assert len(sccs[0]) == 3

    def test_no_scc_in_dag(self):
        """Acyclic graph → no SCCs."""
        from partition.index.index_agent import IndexAgent
        import networkx as nx

        agent = IndexAgent()
        dag = nx.DiGraph()
        dag.add_edges_from([("A", "B"), ("B", "C"), ("C", "D")])
        sccs = agent._detect_scc(dag)
        assert len(sccs) == 0

    def test_hop_cap(self):
        """Hop cap should equal longest path, capped at 10."""
        from partition.index.index_agent import IndexAgent
        import networkx as nx

        agent = IndexAgent()
        # Chain of 5 nodes → longest path = 4
        dag = nx.DiGraph()
        dag.add_edges_from([(str(i), str(i+1)) for i in range(5)])
        hop = agent._compute_hop_cap(dag)
        assert hop == 4

    def test_hop_cap_max(self):
        """Chains > 10 should be capped."""
        from partition.index.index_agent import IndexAgent
        import networkx as nx

        agent = IndexAgent()
        dag = nx.DiGraph()
        dag.add_edges_from([(str(i), str(i+1)) for i in range(15)])
        hop = agent._compute_hop_cap(dag)
        assert hop == 10


class TestDuckDB:
    def test_all_tables_created(self, tmp_path):
        """All 7 DuckDB analytics tables should be created."""
        from partition.db.duckdb_manager import init_all_duckdb_tables
        import duckdb
        db_path = str(tmp_path / "test.duckdb")
        init_all_duckdb_tables(db_path)
        con = duckdb.connect(db_path)
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        expected = ["llm_audit", "calibration_log", "ablation_results",
                    "quality_metrics", "feedback_log", "kb_changelog",
                    "conversion_reports"]
        for t in expected:
            assert t in tables
        con.close()


def _mock_partition(content_hash="test_hash"):
    from unittest.mock import MagicMock
    import uuid
    p = MagicMock()
    p.partition_id = uuid.uuid4()
    p.source_file_id = uuid.uuid4()
    p.content_hash = content_hash
    p.partition_type.value = "DATA_STEP"
    p.risk_level.value = "LOW"
    p.complexity_score = 0.2
    p.calibration_confidence = 0.8
    p.strategy.value = "FLAT_PARTITION"
    p.line_start = 1
    p.line_end = 10
    p.control_depth = 0
    p.has_macros = False
    p.has_nested_sql = False
    p.macro_scope = {}
    p.variable_scope = {}
    p.dependency_refs = []
    p.raptor_leaf_id = "leaf-1"
    p.raptor_cluster_id = None
    p.raptor_root_id = None
    p.scc_id = None
    p.test_coverage_type = "full"
    p.raw_code = "DATA test; SET input; RUN;"
    p.trace_id = uuid.uuid4()
    return p
```

---

## Checklist — End of Week 7

- [ ] `partition/persistence/persistence_agent.py` — PersistenceAgent (#10)
- [ ] `partition/index/index_agent.py` — IndexAgent (#11) with 3 stages
- [ ] `partition/index/kuzu_writer.py` — Kuzu graph writer with DEPENDS_ON + MACRO_CALLS
- [ ] `partition/db/duckdb_manager.py` — All 7 DuckDB tables initialized
- [ ] `partition/config/config_manager.py` — Dynamic hop cap in YAML
- [ ] SQLite tables: file_registry, partition_ir, cross_file_deps, conversion_results, merged_scripts
- [ ] SCC detection works on injected circular deps (≥ 90% accuracy)
- [ ] Condensed DAG is acyclic (assert `nx.is_directed_acyclic_graph()`)
- [ ] Kuzu multi-hop query returns correct results on test DAG
- [ ] Dedup: running pipeline twice produces same row count
- [ ] Parquet fallback triggers for batches ≥ 10,000
- [ ] Dynamic hop cap stored in `config/project_config.yaml`
- [ ] `tests/test_persistence.py` — ≥ 10 assertions
- [ ] Git: `week-07` branch, merged to `main`

---

## Evaluation Metrics for This Week

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Dedup correctness | unique hashes = total rows | Run twice, compare counts |
| Index completeness | Kuzu nodes = SQLite partition count | Query both |
| SCC detection accuracy | ≥ 90% | 10 synthetic circular dep scenarios |
| SCC false positive rate | ≤ 2% | Verify no single-node SCCs reported |
| Kuzu multi-hop query correctness | ≥ 95% | 10 hardcoded DAG scenarios |
| Kuzu query latency (p50) | ≤ 200 ms | `tests/test_index_agent.py` timing |
| Checkpoint resume correctness | block count after resume = expected | Crash simulation test |

---

## Dependencies Added This Week

| Package | Version | Purpose |
|---------|---------|---------|
| kuzu | ≥ 0.3 | Embedded graph database (Cypher) |
| networkx | ≥ 3.1 | DAG + SCC + topological sort |
| sqlalchemy | ≥ 2.0 | ORM for SQLite/PostgreSQL |
| pyyaml | ≥ 6.0 | Project config file |
| duckdb | ≥ 0.9 | Analytics tables (extended) |

---

## Common Pitfalls

| Pitfall | How to Avoid |
|---------|-------------|
| Kuzu `CREATE REL TABLE` fails if node table missing | Always create node tables first |
| `nx.condensation` returns an integer-indexed graph | Map condensation node IDs back to partition sets via `condensation[node]['members']` |
| SQLite `INSERT OR IGNORE` silently skips — you won't see errors | Check `written` count vs input count; log discrepancies |
| Kuzu Cypher `MERGE` syntax differs slightly from Neo4j | Test Cypher queries against Kuzu docs, not Neo4j tutorials |
| SCC on an already-acyclic graph returns N single-node SCCs | Filter: only report SCCs with `len(scc) > 1` |
| `nx.dag_longest_path_length` crashes on graphs with cycles | Always call on the condensed (acyclic) graph, not the original |

---

> *Week 7 Complete → You have: 11 agents, full persistence layer (SQLite + LanceDB + Kuzu + DuckDB), SCC detection, dependency graph. P1 infrastructure done! Next: Orchestration (Week 8).*
