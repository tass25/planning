# Week 7 Visualization: Persistence & Index Layer

> Artifacts produced:
> - `partition_graph.gpickle` (NetworkX dependency graph)
> - `analytics.duckdb` (DuckDB analytics tables)
> - Extended `file_registry.db` (SQLite: partition_ir, conversion_results, merged_scripts)

**Branch note:** All these databases are created on `main` when you run the pipeline.

---

## 1. NetworkX Dependency Graph

### Check if graph exists

```powershell
Test-Path .\partition_graph.gpickle
```

### Quick stats: node/edge counts

```powershell
python -c "import networkx as nx; import pickle; g=pickle.load(open('partition_graph.gpickle','rb')); print('Nodes:', g.number_of_nodes()); print('Edges:', g.number_of_edges())"
```

### View sample node metadata (first 3 nodes)

```powershell
python -c "
import networkx as nx
import pickle

g = pickle.load(open('partition_graph.gpickle', 'rb'))
nodes = list(g.nodes(data=True))[:3]
print('Sample nodes:')
for nid, attrs in nodes:
    print(f'  {nid}:')
    print(f'    partition_type: {attrs.get(\"partition_type\")}')
    print(f'    risk_level: {attrs.get(\"risk_level\")}')
    print(f'    scc_id: {attrs.get(\"scc_id\")}')
    print()
"
```

### Count nodes per partition_type

```powershell
python -c "
import networkx as nx
import pickle
from collections import Counter

g = pickle.load(open('partition_graph.gpickle', 'rb'))
types = [attrs.get('partition_type', 'unknown') for _, attrs in g.nodes(data=True)]
print('Nodes by partition_type:')
for ptype, count in sorted(Counter(types).items()):
    print(f'  {ptype}: {count}')
"
```

### Count SCCs (strongly connected components)

```powershell
python -c "
import networkx as nx
import pickle

g = pickle.load(open('partition_graph.gpickle', 'rb'))
scc_ids = {attrs.get('scc_id') for _, attrs in g.nodes(data=True) if attrs.get('scc_id')}
print(f'Total SCCs detected: {len(scc_ids)}')
"
```

### View edges with types (first 5)

```powershell
python -c "
import networkx as nx
import pickle

g = pickle.load(open('partition_graph.gpickle', 'rb'))
edges = list(g.edges(data=True))[:5]
print('Sample edges:')
for src, tgt, attrs in edges:
    edge_type = attrs.get('edge_type', 'DEPENDS_ON')
    print(f'  {src[:8]}... -> {tgt[:8]}... [{edge_type}]')
"
```

### Multi-hop traversal query (example: get deps of a node)

```powershell
python -c "
import networkx as nx
import pickle

g = pickle.load(open('partition_graph.gpickle', 'rb'))
if g.number_of_nodes() == 0:
    print('Graph is empty')
else:
    # Pick first node as example
    start_node = list(g.nodes())[0]
    # BFS up to 3 hops
    visited = set()
    current = {start_node}
    for hop in range(3):
        next_level = set()
        for node in current:
            for succ in g.successors(node):
                if succ not in visited and succ != start_node:
                    visited.add(succ)
                    next_level.add(succ)
        current = next_level
        if not current:
            break
    print(f'Node {start_node[:8]}... has {len(visited)} dependencies within 3 hops')
"
```

---

## 2. DuckDB Analytics Tables

### Check if DuckDB file exists

```powershell
Test-Path .\analytics.duckdb
```

### List all tables

```powershell
python -c "import duckdb; con=duckdb.connect('analytics.duckdb'); print('Tables:'); [print(f'  - {r[0]}') for r in con.execute('SHOW TABLES').fetchall()]; con.close()"
```

### Count rows in each analytics table

```powershell
python -c "
import duckdb
con = duckdb.connect('analytics.duckdb')
tables = ['llm_audit', 'calibration_log', 'ablation_results', 'quality_metrics', 'feedback_log', 'kb_changelog', 'conversion_reports']
print('Row counts:')
for tbl in tables:
    try:
        count = con.execute(f'SELECT COUNT(*) FROM {tbl}').fetchone()[0]
        print(f'  {tbl}: {count}')
    except Exception as e:
        print(f'  {tbl}: error ({e})')
con.close()
"
```

### View recent LLM audit log (last 5 calls)

```powershell
python -c "import duckdb; con=duckdb.connect('analytics.duckdb'); rows=con.execute('SELECT agent_name, model_name, success, latency_ms FROM llm_audit ORDER BY timestamp DESC LIMIT 5').fetchall(); print('Recent LLM calls:'); [print(f'  {r[0]} | {r[1]} | success={r[2]} | {r[3]:.1f}ms') for r in rows]; con.close()"
```

### View calibration history

```powershell
python -c "import duckdb; con=duckdb.connect('analytics.duckdb'); rows=con.execute('SELECT ece_score, n_samples, model_version, created_at FROM calibration_log ORDER BY created_at DESC LIMIT 3').fetchall(); print('Calibration runs:'); [print(f'  ECE={r[0]:.4f} n={r[1]} version={r[2]} at={r[3]}') for r in rows]; con.close()"
```

---

## 3. SQLite Extended Tables (Week 7 additions)

### New tables added this week:
- `partition_ir` — every PartitionIR persisted
- `conversion_results` — translation outputs
- `merged_scripts` — final merged .py files

### Count partitions persisted

```powershell
python -c "import sqlite3; con=sqlite3.connect('file_registry.db'); cur=con.cursor(); cur.execute('SELECT COUNT(*) FROM partition_ir'); print('partition_ir rows:', cur.fetchone()[0]); con.close()"
```

### Count by partition_type

```powershell
python -c "
import sqlite3
con = sqlite3.connect('file_registry.db')
cur = con.cursor()
cur.execute('SELECT partition_type, COUNT(*) FROM partition_ir GROUP BY partition_type')
print('Partitions by type:')
for ptype, count in cur.fetchall():
    print(f'  {ptype}: {count}')
con.close()
"
```

### Count by risk_level

```powershell
python -c "
import sqlite3
con = sqlite3.connect('file_registry.db')
cur = con.cursor()
cur.execute('SELECT risk_level, COUNT(*) FROM partition_ir GROUP BY risk_level')
print('Partitions by risk_level:')
for rlvl, count in cur.fetchall():
    print(f'  {rlvl}: {count}')
con.close()
"
```

### Count conversion results by validation_status

```powershell
python -c "
import sqlite3
con = sqlite3.connect('file_registry.db')
cur = con.cursor()
try:
    cur.execute('SELECT validation_status, COUNT(*) FROM conversion_results GROUP BY validation_status')
    print('Conversion results by status:')
    for status, count in cur.fetchall():
        print(f'  {status}: {count}')
except Exception as e:
    print(f'conversion_results table empty or not created yet: {e}')
con.close()
"
```

### View sample partition (with RAPTOR back-links)

```powershell
python -c "
import sqlite3
con = sqlite3.connect('file_registry.db')
cur = con.cursor()
cur.execute('SELECT partition_id, partition_type, risk_level, raptor_leaf_id, scc_id FROM partition_ir LIMIT 3')
print('Sample partitions:')
for row in cur.fetchall():
    print(f'  ID: {row[0][:8]}... type={row[1]} risk={row[2]}')
    print(f'    raptor_leaf={row[3][:8] if row[3] else None}... scc={row[4] or \"none\"}')
con.close()
"
```
