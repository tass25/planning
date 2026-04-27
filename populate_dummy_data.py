"""populate_dummy_data.py — Fill databases with dummy data for visualization testing."""

import sys
from pathlib import Path
from datetime import datetime
import random

# Add sas_converter to path
_REPO_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(_REPO_ROOT / "sas_converter"))


def populate_sqlite():
    """Add dummy data to file_registry.db"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from partition.db.sqlite_manager import (
        FileRegistryRow, CrossFileDependencyRow, DataLineageRow,
        PartitionIRRow, get_engine
    )
    
    print("Populating file_registry.db...")
    engine = get_engine("file_registry.db")
    session = Session(engine)
    
    # Add 10 dummy files
    file_ids = []
    for i in range(1, 11):
        file_id = f"file_{i:03d}"
        file_ids.append(file_id)
        fr = FileRegistryRow(
            file_id=file_id,
            file_path=f"sas_converter/knowledge_base/gold_standard/gs_{i:02d}_test.sas",
            encoding="utf-8",
            content_hash=f"hash_{i:03d}",
            file_size_bytes=random.randint(1000, 50000),
            line_count=random.randint(20, 500),
            lark_valid=True,
            lark_errors="",
            status="COMPLETED",
            error_log="",
            created_at=datetime.now().isoformat()
        )
        session.add(fr)
    
    session.commit()  # Commit files first before adding foreign key references
    
    # Add 15 cross-file dependencies
    for i in range(15):
        src = random.choice(file_ids)
        tgt = random.choice([f for f in file_ids if f != src])
        dep = CrossFileDependencyRow(
            source_file_id=src,
            ref_type=random.choice(["INCLUDE", "LIBNAME", "MACRO_CALL"]),
            raw_reference=f"%include {tgt}.sas",
            target_file_id=tgt,
            resolved=True
        )
        session.add(dep)
    
    session.commit()  # Commit dependencies before lineage
    
    # Add 20 data lineage entries
    datasets = ["raw.customers", "raw.orders", "staging.customers_clean", 
                "staging.orders_clean", "mart.sales_summary", "mart.customer_360"]
    for i in range(20):
        lineage = DataLineageRow(
            source_file_id=random.choice(file_ids),
            lineage_type=random.choice(["TABLE_READ", "TABLE_WRITE"]),
            source_dataset=random.choice(datasets[:4]) if i % 2 == 0 else None,
            target_dataset=random.choice(datasets[2:]) if i % 2 == 1 else None,
            source_columns='["col1", "col2"]',
            target_column="result_col",
            transform_expr="SUM(col1 * col2)",
            block_line_start=i * 10 + 1,
            block_line_end=i * 10 + 5
        )
        session.add(lineage)
    
    session.commit()  # Commit lineage before partitions
    
    # Add 50 partition IR entries
    partition_types = ["DATA_STEP", "PROC_BLOCK", "MACRO_DEFINITION", "SQL_BLOCK", 
                       "LOOP_BLOCK", "CONDITIONAL_BLOCK", "MACRO_INVOCATION"]
    risk_levels = ["LOW", "MODERATE", "HIGH"]
    
    for i in range(50):
        partition = PartitionIRRow(
            partition_id=f"partition_{i:03d}",
            source_file_id=random.choice(file_ids),
            partition_type=random.choice(partition_types),
            risk_level=random.choice(risk_levels),
            conversion_status="PENDING",
            content_hash=f"hash_partition_{i:03d}",
            complexity_score=random.uniform(0.1, 0.9),
            calibration_confidence=random.uniform(0.5, 0.95),
            strategy="FLAT_PARTITION",
            line_start=i * 10 + 1,
            line_end=i * 10 + random.randint(5, 20),
            control_depth=random.randint(0, 3),
            has_macros=random.choice([True, False]),
            has_nested_sql=random.choice([True, False]),
            raw_code=f"/* Dummy partition {i} */\nDATA test_{i};\n  SET source;\nRUN;",
            raptor_leaf_id=f"leaf_{i:03d}",
            raptor_cluster_id=f"cluster_{i // 10:02d}",
            raptor_root_id="root_001",
            scc_id="" if random.random() > 0.1 else f"scc_{random.randint(1, 3)}",
            created_at=datetime.now().isoformat()
        )
        session.add(partition)
    
    session.commit()
    session.close()
    print(f"  Added: 10 files, 15 dependencies, 20 lineage, 50 partitions")


def populate_duckdb():
    """Add dummy data to analytics.duckdb"""
    import duckdb
    
    print("Populating analytics.duckdb...")
    conn = duckdb.connect("analytics.duckdb")
    
    # LLM audit logs
    for i in range(20):
        conn.execute("""
            INSERT INTO llm_audit VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NOW())
        """, [
            f"call_{i:03d}",
            random.choice(["BoundaryDetectorAgent", "ComplexityAgent", "RAPTORAgent"]),
            random.choice(["llama3.1:8b", "groq/llama-70b", "heuristic"]),
            f"prompt_hash_{i}",
            f"response_hash_{i}",
            random.uniform(50, 5000),
            random.choice([True, True, True, False]),  # 75% success
            "" if random.random() > 0.25 else f"Error {i}",
            random.choice(["primary", "fallback", "heuristic"])
        ])
    
    # Calibration logs
    for i in range(5):
        conn.execute("""
            INSERT INTO calibration_log VALUES (?, ?, ?, ?, ?, NOW())
        """, [
            f"calib_{i:03d}",
            round(random.uniform(0.04, 0.08), 4),
            random.randint(500, 800),
            random.randint(400, 600),
            f"logistic_v{i+1}"
        ])
    
    conn.close()
    print(f"  Added: 20 llm_audit, 5 calibration_log entries")


def populate_networkx():
    """Add dummy data to partition_graph.gpickle"""
    import pickle
    import networkx as nx
    
    print("Populating partition_graph.gpickle...")
    
    G = nx.DiGraph()
    
    # Add 50 partition nodes
    partition_types = ["DATA_STEP", "PROC_BLOCK", "MACRO_DEFINITION", "SQL_BLOCK"]
    risk_levels = ["LOW", "MODERATE", "HIGH"]
    
    for i in range(50):
        pid = f"partition_{i:03d}"
        G.add_node(
            pid,
            partition_type=random.choice(partition_types),
            risk_level=random.choice(risk_levels),
            complexity_score=random.uniform(0.1, 0.9),
            file_id=f"file_{random.randint(1, 10):03d}",
            scc_id=""
        )
    
    # Add 60 edges (dependencies)
    nodes = list(G.nodes())
    for _ in range(60):
        src = random.choice(nodes)
        tgt = random.choice([n for n in nodes if n != src])
        if not G.has_edge(src, tgt):  # Avoid duplicates
            G.add_edge(src, tgt, edge_type=random.choice(["DEPENDS_ON", "MACRO_CALLS"]))
    
    # Add 3 SCCs (circular dependencies)
    sccs = list(nx.strongly_connected_components(G))
    scc_count = len([s for s in sccs if len(s) > 1])
    
    with open("partition_graph.gpickle", "wb") as f:
        pickle.dump(G, f)
    
    print(f"  Added: 50 nodes, 60 edges, {scc_count} SCCs")


def populate_lancedb():
    """Create dummy lancedb_data/ folder with sample data"""
    import lancedb
    import pyarrow as pa
    
    print("Populating lancedb_data/...")
    
    try:
        db = lancedb.connect("lancedb_data")
        
        # Create schema for RAPTOR nodes
        schema = pa.schema([
            pa.field("node_id", pa.string()),
            pa.field("level", pa.int32()),
            pa.field("summary_text", pa.string()),
            pa.field("summary_tier", pa.string()),
            pa.field("parent_id", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), 768))
        ])
        
        # Generate 100 dummy nodes across 3 levels
        data = []
        for i in range(100):
            level = random.choice([0, 1, 2])
            data.append({
                "node_id": f"node_{i:03d}",
                "level": level,
                "summary_text": f"Summary of partition group {i}. This is a test node at level {level}.",
                "summary_tier": random.choice(["groq", "ollama_fallback", "heuristic_fallback", "cached"]),
                "parent_id": f"node_{max(0, i-10):03d}" if level > 0 else "",
                "embedding": [random.uniform(-1, 1) for _ in range(768)]
            })
        
        # Create table
        table = db.create_table("raptor_nodes", data=data, mode="overwrite")
        
        print(f"  Added: 100 RAPTOR nodes across 3 levels")
        
    except Exception as e:
        print(f"  WARNING: Could not create LanceDB: {e}")
        print(f"  Install pyarrow if needed: pip install pyarrow")


def main():
    print("=" * 70)
    print("Populating databases with dummy data...")
    print("=" * 70 + "\n")
    
    populate_sqlite()
    populate_duckdb()
    populate_networkx()
    populate_lancedb()
    
    print("\n" + "=" * 70)
    print("Dummy data populated! Now run:")
    print("  python planning/week01_02viz.py")
    print("  python planning/week03_04viz.py")
    print("  python planning/week04viz.py")
    print("  python planning/week05_06viz.py")
    print("  python planning/week07viz.py")
    print("=" * 70)


if __name__ == "__main__":
    main()
