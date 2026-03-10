"""Week 5-6 Visualization: RAPTOR Tree in LanceDB

Shows:
- RAPTOR tree structure (level distribution)
- Summary tier fallback chain usage
- Embedding space projection (t-SNE)
- Interactive node hover info

Run from repo root on main:
    python planning/week05_06viz.py
"""

import sys
import json
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.patches import Circle, FancyBboxPatch
except ImportError:
    print("ERROR: Install matplotlib + numpy:")
    print("  pip install matplotlib numpy")
    sys.exit(1)

try:
    import lancedb
except ImportError:
    print("ERROR: Install lancedb:")
    print("  pip install lancedb")
    sys.exit(1)

#  Config 
DB_PATH = "lancedb_data"
TABLE_NAME = "raptor_nodes"

if not Path(DB_PATH).exists():
    print(f"ERROR: {DB_PATH} folder not found.")
    print("Switch to main branch and run the RAPTOR pipeline first.")
    sys.exit(1)

print("=" * 70)
print("WEEK 5-6: RAPTOR Tree in LanceDB")
print("=" * 70)

#  Load RAPTOR nodes 
db = lancedb.connect(DB_PATH)

if TABLE_NAME not in db.table_names():
    print(f"ERROR: Table '{TABLE_NAME}' not found in {DB_PATH}.")
    print("Run the RAPTOR agent first to populate the tree.")
    sys.exit(1)

table = db.open_table(TABLE_NAME)
rows = table.search().limit(1000).to_list()

if not rows:
    print("No RAPTOR nodes found. Run the pipeline first.")
    sys.exit(1)

print(f"\nTotal RAPTOR nodes: {len(rows)}")

#  Parse node data 
levels = [r['level'] for r in rows]
summary_tiers = [r['summary_tier'] for r in rows]
embeddings = [r['embedding'] for r in rows]

level_counts = {}
for lvl in levels:
    level_counts[lvl] = level_counts.get(lvl, 0) + 1

tier_counts = {}
for tier in summary_tiers:
    tier_counts[tier] = tier_counts.get(tier, 0) + 1

print("\nLevel distribution:")
for lvl in sorted(level_counts.keys()):
    print(f"   Level {lvl}: {level_counts[lvl]} nodes")

print("\n Summary tier distribution:")
for tier in sorted(tier_counts.keys()):
    print(f"   {tier}: {tier_counts[tier]} nodes")

#  Visualizations 
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))

#  1. Level Distribution Bar Chart 
lvls = sorted(level_counts.keys())
counts = [level_counts[l] for l in lvls]

ax1.bar(lvls, counts, color='steelblue', alpha=0.8, edgecolor='black')
ax1.set_xlabel('RAPTOR Tree Level', fontsize=11)
ax1.set_ylabel('Node Count', fontsize=11)
ax1.set_title('Week 5-6: RAPTOR Level Distribution', fontsize=12, fontweight='bold')
ax1.set_xticks(lvls)
ax1.grid(axis='y', alpha=0.3)

#  2. Summary Tier Pie Chart 
tier_labels = list(tier_counts.keys())
tier_sizes = list(tier_counts.values())
tier_colors = {'groq': 'lightgreen', 'ollama_fallback': 'lightyellow', 
               'heuristic_fallback': 'lightcoral', 'cached': 'lightblue',
               'skipped': 'lightgray'}
colors = [tier_colors.get(t, 'white') for t in tier_labels]

ax2.pie(tier_sizes, labels=tier_labels, colors=colors, autopct='%1.1f%%',
        shadow=True, startangle=90, textprops={'fontsize': 9})
ax2.set_title('Week 5-6: Summary Tier Usage\n(Groq  Ollama  Heuristic)', 
              fontsize=12, fontweight='bold')

#  3. Tree Structure Visualization 
# Sample a few nodes per level for visualization
sample_by_level = {}
for r in rows[:50]:  # Limit to 50 for clarity
    lvl = r['level']
    if lvl not in sample_by_level:
        sample_by_level[lvl] = []
    if len(sample_by_level[lvl]) < 10:
        sample_by_level[lvl].append(r)

max_level = max(sample_by_level.keys())
y_spacing = 1.5
x_spacing = 2.0

for lvl in sorted(sample_by_level.keys()):
    nodes = sample_by_level[lvl]
    y = lvl * y_spacing
    for i, node in enumerate(nodes):
        x = (i - len(nodes)/2) * x_spacing
        
        # Node color by level
        if lvl == 0:
            color = 'lightblue'
        elif lvl == max_level:
            color = 'lightcoral'
        else:
            color = 'lightyellow'
        
        circle = Circle((x, y), 0.3, color=color, ec='black', linewidth=1.5, zorder=3)
        ax3.add_patch(circle)
        
        # Node label (shortened node_id)
        node_id = node['node_id'][:8]
        ax3.text(x, y, node_id, ha='center', va='center', 
                fontsize=6, fontweight='bold', zorder=4)
        
        # Draw edges to children (if child_ids exist)
        child_ids_str = node.get('child_ids', '[]')
        try:
            child_ids = json.loads(child_ids_str) if isinstance(child_ids_str, str) else child_ids_str
            if child_ids and lvl > 0:
                # Draw line down to next level (simplified)
                ax3.plot([x, x], [y, y - y_spacing], 'k-', alpha=0.3, linewidth=1, zorder=1)
        except:
            pass

ax3.set_xlim(-15, 15)
ax3.set_ylim(-1, max_level * y_spacing + 1)
ax3.set_xlabel('Horizontal Spread', fontsize=10)
ax3.set_ylabel('Tree Level', fontsize=10)
ax3.set_title('Week 5-6: RAPTOR Tree Structure (Sample)', fontsize=12, fontweight='bold')
ax3.set_yticks([i * y_spacing for i in range(max_level + 1)])
ax3.set_yticklabels([f'L{i}' for i in range(max_level + 1)])
ax3.grid(True, alpha=0.2)

#  4. Embedding Space Projection (2D PCA) 
if len(embeddings) > 1:
    try:
        from sklearn.decomposition import PCA
        
        # Convert embeddings to numpy array
        emb_matrix = np.array([e[:768] for e in embeddings if len(e) >= 768])
        
        if len(emb_matrix) > 2:
            pca = PCA(n_components=2)
            emb_2d = pca.fit_transform(emb_matrix)
            
            # Color by level
            colors_scatter = [plt.cm.viridis(r['level'] / max(levels)) for r in rows[:len(emb_2d)]]
            
            scatter = ax4.scatter(emb_2d[:, 0], emb_2d[:, 1], c=colors_scatter, 
                                 s=50, alpha=0.7, edgecolors='black', linewidth=0.5)
            ax4.set_xlabel('PCA Component 1', fontsize=10)
            ax4.set_ylabel('PCA Component 2', fontsize=10)
            ax4.set_title('Week 5-6: RAPTOR Embedding Space (PCA Projection)', 
                         fontsize=12, fontweight='bold')
            
            # Colorbar for level
            from matplotlib.colorbar import ColorbarBase
            from matplotlib.colors import Normalize
            norm = Normalize(vmin=0, vmax=max(levels))
            sm = plt.cm.ScalarMappable(cmap=plt.cm.viridis, norm=norm)
            sm.set_array([])
            cbar = plt.colorbar(sm, ax=ax4)
            cbar.set_label('Tree Level', fontsize=10)
            
            ax4.grid(True, alpha=0.3)
        else:
            ax4.text(0.5, 0.5, 'Not enough embeddings for PCA', 
                    ha='center', va='center', fontsize=11)
            ax4.set_xlim(0, 1)
            ax4.set_ylim(0, 1)
    except ImportError:
        ax4.text(0.5, 0.5, 'Install scikit-learn for PCA:\npip install scikit-learn', 
                ha='center', va='center', fontsize=11)
        ax4.set_xlim(0, 1)
        ax4.set_ylim(0, 1)
else:
    ax4.text(0.5, 0.5, 'Not enough embeddings', ha='center', va='center', fontsize=11)
    ax4.set_xlim(0, 1)
    ax4.set_ylim(0, 1)

plt.tight_layout()
plt.show()

print("\n Week 5-6 visualization complete.")
print(f"   RAPTOR tree: {len(rows)} nodes across {len(level_counts)} levels")
print(f"   Summary tiers: {', '.join(tier_counts.keys())}")
