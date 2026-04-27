# Week 5–6 Visualization: RAPTOR Tree in LanceDB

> Artifacts produced: `lancedb_data/` folder (LanceDB vector store)

**Branch note:** This database is created on `main` when you run the RAPTOR pipeline.

---

## 1. LanceDB: raptor_nodes table

### Check if LanceDB folder exists

```powershell
Test-Path .\lancedb_data
```

### List tables in LanceDB

```powershell
python -c "import lancedb; db=lancedb.connect('lancedb_data'); print('Tables:', db.table_names())"
```

### Count RAPTOR nodes

```powershell
python -c "import lancedb; db=lancedb.connect('lancedb_data'); t=db.open_table('raptor_nodes'); print('raptor_nodes rows:', len(t))"
```

### View sample nodes (first 3)

```powershell
python -c "
import lancedb
db = lancedb.connect('lancedb_data')
t = db.open_table('raptor_nodes')
rows = t.search().limit(3).to_list()
print('Sample RAPTOR nodes:')
for r in rows:
    print(f\"  node_id: {r['node_id']}\")
    print(f\"    level: {r['level']}\")
    print(f\"    summary_tier: {r['summary_tier']}\")
    print(f\"    file_id: {r['file_id']}\")
    print(f\"    embedding dim: {len(r['embedding'])}\")
    print()
"
```

### Count nodes per level (tree depth distribution)

```powershell
python -c "
import lancedb
from collections import Counter
db = lancedb.connect('lancedb_data')
t = db.open_table('raptor_nodes')
rows = t.search().limit(10000).to_list()
levels = [r['level'] for r in rows]
print('Nodes per level:')
for lvl, count in sorted(Counter(levels).items()):
    print(f'  Level {lvl}: {count} nodes')
"
```

### Count nodes by summary_tier (LLM fallback chain usage)

```powershell
python -c "
import lancedb
from collections import Counter
db = lancedb.connect('lancedb_data')
t = db.open_table('raptor_nodes')
rows = t.search().limit(10000).to_list()
tiers = [r['summary_tier'] for r in rows]
print('Summary tier distribution:')
for tier, count in sorted(Counter(tiers).items()):
    print(f'  {tier}: {count}')
"
```

### Query similar nodes (cosine search example)

```powershell
python -c "
import lancedb
db = lancedb.connect('lancedb_data')
t = db.open_table('raptor_nodes')

# Get one node's embedding as query
sample = t.search().limit(1).to_list()[0]
query_emb = sample['embedding']

# Find 5 nearest neighbors
results = t.search(query_emb).limit(5).to_list()
print('Top 5 similar nodes:')
for i, r in enumerate(results, 1):
    print(f\"{i}. node_id={r['node_id'][:8]}... level={r['level']} tier={r['summary_tier']}\")
"
```

---

## 2. Inspect RAPTOR parameters used (from code)

- **Embedding model:** Nomic Embed v1.5 (768-dim)
- **Clustering:** GMM with k ∈ [2, √N capped at 20]
- **Soft-assignment threshold (τ):** 0.72
- **BIC convergence delta:** 0.01
- **Dynamic depth:** max_depth=5 if `macro_density > 0.4`, else 3
- **LLM fallback chain:** Groq → Ollama → heuristic

Check the current GMM parameters:

```powershell
python -c "
from partition.raptor.clustering import GMMClusterer
c = GMMClusterer()
print('GMM config:')
print(f'  tau: {c.tau}')
print(f'  bic_epsilon: {c.bic_epsilon}')
print(f'  reg_covar: {c.reg_covar}')
"
```
