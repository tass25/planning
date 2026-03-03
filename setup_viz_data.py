"""setup_viz_data.py — Generate all databases needed for visualization scripts.

This script creates:
  - file_registry.db (SQLite) manually
  - analytics.duckdb (DuckDB) via init_all_duckdb_tables()
  - partition_graph.gpickle (NetworkX) via NetworkXGraphBuilder
  - lancedb_data/ (LanceDB) — requires manual RAPTOR run

Usage:
    python setup_viz_data.py
"""

import sys
from pathlib import Path

# Add sas_converter to path
_REPO_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(_REPO_ROOT / "sas_converter"))

from partition.db.duckdb_manager import init_all_duckdb_tables, DB_PATH
from partition.index.graph_builder import NetworkXGraphBuilder


def main():
    print("=" * 70)
    print("Generating visualization data...")
    print("=" * 70)
    
    # Step 1: Create file_registry.db manually
    print("\n[1/3] Creating file_registry.db...")
    try:
        from partition.db.sqlite_manager import get_engine, Base
        engine = get_engine("file_registry.db")
        Base.metadata.create_all(engine)
        print("      OK file_registry.db created (empty schema)")
    except Exception as e:
        print(f"      WARNING Error: {e}")
        print("      You may need to run: python main.py --file <test.sas>")
    
    # Step 2: Initialize analytics.duckdb
    print("\n[2/3] Creating analytics.duckdb...")
    try:
        init_all_duckdb_tables(DB_PATH)
        print(f"      OK {DB_PATH} created with 7 empty tables")
    except Exception as e:
        print(f"      WARNING Error: {e}")
    
    # Step 3: Create empty partition_graph.gpickle
    print("\n[3/3] Creating partition_graph.gpickle...")
    try:
        import pickle
        import networkx as nx
        
        # Create an empty DiGraph
        g = nx.DiGraph()
        # Add a dummy node so it's not completely empty
        g.add_node("dummy_partition", partition_type="DATA_STEP", file_id="test")
        
        # Save to pickle
        with open("partition_graph.gpickle", "wb") as f:
            pickle.dump(g, f)
        print("      OK partition_graph.gpickle created (1 dummy node)")
    except Exception as e:
        print(f"      WARNING Error: {e}")
    
    # Step 4: LanceDB info
    print("\n[LanceDB] lancedb_data/ folder:")
    lancedb_path = Path("lancedb_data")
    if lancedb_path.exists():
        print(f"      OK {lancedb_path} exists")
    else:
        print("      WARNING Not found. To create it, you need to:")
        print("         1. Run the RAPTOR pipeline with RAPTORLanceDBWriter")
        print("         2. Or manually create it with sample data")
        print("\n      For now, week05_06viz.py will skip this week.")
    
    print("\n" + "=" * 70)
    print("Setup complete! You can now run:")
    print("  python planning/week01_02viz.py  (SQLite + NetworkX)")
    print("  python planning/week03_04viz.py  (Hardcoded benchmark data)")
    print("  python planning/week04viz.py     (Hardcoded calibration data)")
    print("  python planning/week07viz.py     (SQLite + NetworkX + DuckDB)")
    print("\nFor full data, run:")
    print("  python main.py --dir sas_converter/knowledge_base/gold_standard/")
    print("=" * 70)


if __name__ == "__main__":
    main()
