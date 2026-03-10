"""Week 1-2 Visualization: File Registry + Dependencies + Data Lineage

Run this from repo root on main branch:
    python planning/week01_02viz.py

Shows:
- File registry table stats
- Cross-file dependency graph (interactive)
- Data lineage flow diagram
"""

import sqlite3
import sys
from pathlib import Path

try:
    import networkx as nx
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch
except ImportError:
    print("ERROR: Install networkx + matplotlib:")
    print("  pip install networkx matplotlib")
    sys.exit(1)

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = "file_registry.db"

# ── Helper: Check DB exists ───────────────────────────────────────────────────
if not Path(DB_PATH).exists():
    print(f"ERROR: {DB_PATH} not found.")
    print("Switch to main branch and run the pipeline first to generate the DB.")
    sys.exit(1)

con = sqlite3.connect(DB_PATH)
cur = con.cursor()

# ── 1. File Registry Stats ────────────────────────────────────────────────────
print("=" * 70)
print("WEEK 1-2: File Registry + Dependencies + Data Lineage")
print("=" * 70)

cur.execute("SELECT COUNT(*) FROM file_registry")
file_count = cur.fetchone()[0]
print(f"\nTotal SAS files scanned: {file_count}")

if file_count == 0:
    print("\n⚠️  No data in file_registry.db yet.")
    print("   Run: python main.py --dir sas_converter/knowledge_base/gold_standard/")
    print("   to populate the database with real data.\n")
    con.close()
    sys.exit(0)

cur.execute("SELECT encoding, COUNT(*) FROM file_registry GROUP BY encoding")
encodings = cur.fetchall()
print("\nEncoding distribution:")
for enc, cnt in encodings:
    print(f"   {enc}: {cnt} files")

cur.execute("SELECT AVG(line_count), MAX(line_count) FROM file_registry")
avg_lines, max_lines = cur.fetchone()
print(f"\nLines per file: avg={avg_lines:.0f}, max={max_lines}")

# ── 2. Cross-File Dependency Graph ─────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM cross_file_deps")
dep_count = cur.fetchone()[0]
print(f"\nCross-file dependencies: {dep_count}")

if dep_count > 0:
    cur.execute("""
        SELECT cf.source_file_id, cf.target_file_id, cf.ref_type
        FROM cross_file_deps cf
        WHERE cf.resolved = 1
    """)
    deps = cur.fetchall()

    G_deps = nx.DiGraph()
    for src, tgt, ref_type in deps:
        # Shorten file IDs for display
        src_short = Path(src).stem[:15] if src else "?"
        tgt_short = Path(tgt).stem[:15] if tgt else "?"
        G_deps.add_edge(src_short, tgt_short, label=ref_type)

    print(f"\nDependency graph: {G_deps.number_of_nodes()} files, {G_deps.number_of_edges()} edges")

    if G_deps.number_of_nodes() > 0:
        plt.figure(figsize=(12, 8))
        pos = nx.spring_layout(G_deps, k=1.5, iterations=50)
        
        nx.draw_networkx_nodes(G_deps, pos, node_color='lightblue', 
                               node_size=800, alpha=0.9)
        nx.draw_networkx_labels(G_deps, pos, font_size=8)
        nx.draw_networkx_edges(G_deps, pos, edge_color='gray', 
                               arrows=True, arrowsize=15, alpha=0.6)
        
        edge_labels = nx.get_edge_attributes(G_deps, 'label')
        nx.draw_networkx_edge_labels(G_deps, pos, edge_labels, font_size=7)
        
        plt.title("Week 1-2: Cross-File Dependencies (%INCLUDE, LIBNAME)", 
                  fontsize=14, fontweight='bold')
        plt.axis('off')
        plt.tight_layout()
        plt.show()

# ── 3. Data Lineage Flow ──────────────────────────────────────────────────────
cur.execute("SELECT COUNT(*) FROM data_lineage")
lineage_count = cur.fetchone()[0]
print(f"\nData lineage edges: {lineage_count}")

if lineage_count > 0:
    cur.execute("""
        SELECT source_dataset, target_dataset, lineage_type
        FROM data_lineage
        WHERE source_dataset IS NOT NULL AND target_dataset IS NOT NULL
        LIMIT 100
    """)
    lineage_rows = cur.fetchall()

    G_lineage = nx.DiGraph()
    for src_ds, tgt_ds, ltype in lineage_rows:
        G_lineage.add_edge(src_ds, tgt_ds, type=ltype)

    print(f"🗂️  Lineage graph (sample): {G_lineage.number_of_nodes()} datasets, {G_lineage.number_of_edges()} flows")

    if G_lineage.number_of_nodes() > 0:
        plt.figure(figsize=(14, 10))
        pos = nx.spring_layout(G_lineage, k=2, iterations=50)
        
        # Color nodes by dataset prefix (e.g., raw.* vs staging.* vs mart.*)
        node_colors = []
        for node in G_lineage.nodes():
            if node.startswith('raw.'):
                node_colors.append('lightcoral')
            elif node.startswith('staging.'):
                node_colors.append('lightyellow')
            elif node.startswith('mart.'):
                node_colors.append('lightgreen')
            else:
                node_colors.append('lightgray')
        
        nx.draw_networkx_nodes(G_lineage, pos, node_color=node_colors, 
                               node_size=600, alpha=0.9)
        nx.draw_networkx_labels(G_lineage, pos, font_size=7)
        nx.draw_networkx_edges(G_lineage, pos, edge_color='gray', 
                               arrows=True, arrowsize=12, alpha=0.5)
        
        plt.title("Week 1-2: Data Lineage (TABLE_READ / TABLE_WRITE)", 
                  fontsize=14, fontweight='bold')
        
        # Legend
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='lightcoral', label='raw.*'),
            Patch(facecolor='lightyellow', label='staging.*'),
            Patch(facecolor='lightgreen', label='mart.*')
        ]
        plt.legend(handles=legend_elements, loc='upper right')
        
        plt.axis('off')
        plt.tight_layout()
        plt.show()

con.close()
print("\n✅ Week 1-2 visualization complete.")
