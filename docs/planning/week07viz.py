"""Week 7 Visualization: Persistence + Index + NetworkX Graph + DuckDB Analytics

Shows:
- SQLite partition persistence stats
- NetworkX dependency graph (interactive with SCC highlighting)
- DuckDB analytics table summaries
- Dynamic hop cap + SCC analysis

Run from repo root on main:
    python planning/week07viz.py
"""

import sys
import sqlite3
import pickle
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
    import networkx as nx
    from matplotlib.patches import FancyBboxPatch
except ImportError:
    print("ERROR: Install networkx + matplotlib + numpy:")
    print("  pip install networkx matplotlib numpy")
    sys.exit(1)

try:
    import duckdb
except ImportError:
    print("ERROR: Install duckdb:")
    print("  pip install duckdb")
    sys.exit(1)

#  Config 
SQLITE_DB = "file_registry.db"
DUCKDB_FILE = "analytics.duckdb"
NX_GRAPH_PICKLE = "partition_graph.gpickle"

print("=" * 70)
print("WEEK 7: Persistence + Index + NetworkX + DuckDB")
print("=" * 70)

#  1. SQLite partition_ir table stats 
if not Path(SQLITE_DB).exists():
    print(f"\nWARNING: {SQLITE_DB} not found. Skipping SQLite stats.")
else:
    con = sqlite3.connect(SQLITE_DB)
    cur = con.cursor()
    
    # Check if partition_ir table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='partition_ir'")
    if cur.fetchone():
        cur.execute("SELECT COUNT(*) FROM partition_ir")
        partition_count = cur.fetchone()[0]
        
        cur.execute("SELECT risk_level, COUNT(*) FROM partition_ir GROUP BY risk_level")
        risk_dist = dict(cur.fetchall())
        
        cur.execute("SELECT partition_type, COUNT(*) FROM partition_ir GROUP BY partition_type")
        type_dist = dict(cur.fetchall())
        
        print(f"\n SQLite partition_ir: {partition_count} blocks persisted")
        print("\n   Risk level distribution:")
        for risk, count in risk_dist.items():
            print(f"      {risk}: {count}")
        
        print("\n   Partition type distribution (top 5):")
        for ptype, count in sorted(type_dist.items(), key=lambda x: -x[1])[:5]:
            print(f"      {ptype}: {count}")
    else:
        print(f"\n  partition_ir table not found in {SQLITE_DB}")
    
    con.close()

#  2. NetworkX dependency graph 
if not Path(NX_GRAPH_PICKLE).exists():
    print(f"\n  {NX_GRAPH_PICKLE} not found. Skipping NetworkX visualization.")
    G = None
else:
    with open(NX_GRAPH_PICKLE, 'rb') as f:
        G = pickle.load(f)
    
    print(f"\n NetworkX graph loaded:")
    print(f"   Nodes: {G.number_of_nodes()}")
    print(f"   Edges: {G.number_of_edges()}")
    
    # Detect SCCs
    sccs = list(nx.strongly_connected_components(G))
    scc_sizes = [len(scc) for scc in sccs if len(scc) > 1]
    
    print(f"\n Strongly Connected Components (SCCs):")
    print(f"   Total SCCs: {len(sccs)}")
    print(f"   SCCs with >1 node (circular deps): {len(scc_sizes)}")
    if scc_sizes:
        print(f"   Largest SCC size: {max(scc_sizes)}")
    
    # Compute dynamic hop cap (Week 7 feature)
    try:
        longest_path = nx.dag_longest_path_length(G)
    except:
        longest_path = 0  # Graph has cycles
    
    hop_cap = min(longest_path, 10)
    print(f"\n Dynamic hop cap: {hop_cap} (longest_path={longest_path}, capped at 10)")

#  3. DuckDB analytics tables 
if not Path(DUCKDB_FILE).exists():
    print(f"\n  {DUCKDB_FILE} not found. Skipping DuckDB stats.")
else:
    dcon = duckdb.connect(DUCKDB_FILE)
    
    tables = dcon.execute("SHOW TABLES").fetchall()
    table_names = [t[0] for t in tables]
    
    print(f"\n DuckDB analytics ({DUCKDB_FILE}):")
    print(f"   Tables: {len(table_names)}")
    
    for tbl in table_names:
        try:
            count = dcon.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            print(f"      {tbl}: {count} rows")
        except:
            print(f"      {tbl}: (could not count)")
    
    dcon.close()

#  Visualizations 
fig = plt.figure(figsize=(16, 10))
gs = fig.add_gridspec(2, 2, hspace=0.3, wspace=0.3)

ax1 = fig.add_subplot(gs[0, 0])
ax2 = fig.add_subplot(gs[0, 1])
ax3 = fig.add_subplot(gs[1, :])

#  Viz 1: Risk level distribution (if data available) 
if Path(SQLITE_DB).exists():
    con = sqlite3.connect(SQLITE_DB)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='partition_ir'")
    if cur.fetchone():
        cur.execute("SELECT risk_level, COUNT(*) FROM partition_ir GROUP BY risk_level")
        risk_data = dict(cur.fetchall())
        
        labels = list(risk_data.keys())
        sizes = list(risk_data.values())
        colors_pie = {'LOW': 'lightgreen', 'MODERATE': 'lightyellow', 
                      'HIGH': 'lightcoral', 'UNCERTAIN': 'lightgray'}
        colors = [colors_pie.get(l, 'white') for l in labels]
        
        ax1.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%',
                shadow=True, startangle=90, textprops={'fontsize': 10})
        ax1.set_title('Week 7: Risk Level Distribution\n(Persisted Partitions)', 
                     fontsize=11, fontweight='bold')
    else:
        ax1.text(0.5, 0.5, 'partition_ir table\nnot found', ha='center', va='center')
        ax1.set_xlim(0, 1)
        ax1.set_ylim(0, 1)
    con.close()
else:
    ax1.text(0.5, 0.5, f'{SQLITE_DB}\nnot found', ha='center', va='center')
    ax1.set_xlim(0, 1)
    ax1.set_ylim(0, 1)

#  Viz 2: SCC size distribution 
if G is not None:
    sccs = list(nx.strongly_connected_components(G))
    scc_sizes = [len(scc) for scc in sccs]
    scc_size_dist = {}
    for sz in scc_sizes:
        scc_size_dist[sz] = scc_size_dist.get(sz, 0) + 1
    
    sizes_sorted = sorted(scc_size_dist.keys())
    counts = [scc_size_dist[s] for s in sizes_sorted]
    
    ax2.bar(range(len(sizes_sorted)), counts, color='steelblue', alpha=0.8, edgecolor='black')
    ax2.set_xlabel('SCC Size', fontsize=10)
    ax2.set_ylabel('Count', fontsize=10)
    ax2.set_title('Week 7: SCC Size Distribution', fontsize=11, fontweight='bold')
    ax2.set_xticks(range(len(sizes_sorted)))
    ax2.set_xticklabels(sizes_sorted, fontsize=9)
    ax2.grid(axis='y', alpha=0.3)
else:
    ax2.text(0.5, 0.5, f'{NX_GRAPH_PICKLE}\nnot found', ha='center', va='center')
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)

#  Viz 3: NetworkX dependency graph (sample with SCC highlighting) 
if G is not None and G.number_of_nodes() > 0:
    # Take a subgraph if too large
    if G.number_of_nodes() > 50:
        nodes_sample = list(G.nodes())[:50]
        G_sub = G.subgraph(nodes_sample)
    else:
        G_sub = G
    
    # Detect SCCs in subgraph
    sccs_sub = list(nx.strongly_connected_components(G_sub))
    
    # Color nodes by SCC membership
    node_colors = []
    for node in G_sub.nodes():
        in_large_scc = False
        for scc in sccs_sub:
            if len(scc) > 1 and node in scc:
                node_colors.append('lightcoral')  # Circular dependency
                in_large_scc = True
                break
        if not in_large_scc:
            node_colors.append('lightblue')
    
    pos = nx.spring_layout(G_sub, k=2, iterations=50, seed=42)
    
    nx.draw_networkx_nodes(G_sub, pos, node_color=node_colors, 
                           node_size=400, alpha=0.9, ax=ax3)
    nx.draw_networkx_labels(G_sub, pos, font_size=7, ax=ax3)
    nx.draw_networkx_edges(G_sub, pos, edge_color='gray', 
                           arrows=True, arrowsize=10, alpha=0.5, ax=ax3)
    
    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='lightblue', label='Normal node'),
        Patch(facecolor='lightcoral', label='In SCC (circular dep)')
    ]
    ax3.legend(handles=legend_elements, loc='upper right', fontsize=9)
    
    ax3.set_title('Week 7: NetworkX Dependency Graph (Sample)\nRed = SCC (circular dependency)', 
                 fontsize=12, fontweight='bold')
    ax3.axis('off')
else:
    ax3.text(0.5, 0.5, 'No graph data available', ha='center', va='center', fontsize=12)
    ax3.set_xlim(0, 1)
    ax3.set_ylim(0, 1)
    ax3.axis('off')

plt.suptitle('Week 7: Persistence + Index + Analytics', fontsize=14, fontweight='bold')
plt.show()

print("\n Week 7 visualization complete.")
if G is not None:
    print(f"   NetworkX: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"   Dynamic hop cap: {hop_cap}")
    print(f"   SCCs with cycles: {len([s for s in sccs if len(s) > 1])}")
