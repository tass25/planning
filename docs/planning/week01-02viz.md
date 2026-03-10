# Week 1–2 Visualization: SQLite Registry & Lineage

> Artifacts produced: `file_registry.db` (SQLite)

**Branch note:** These databases are created on `main` when you run the pipeline. Switch to `main` to run the inspection commands below.

---

## 1. SQLite: file_registry.db

### Tables created this week
- `file_registry` — discovered .sas files
- `cross_file_deps` — %INCLUDE and LIBNAME references
- `data_lineage` — table-level read/write flows

### Quick inspect: list all tables

```powershell
python -c "import sqlite3; con=sqlite3.connect('file_registry.db'); cur=con.cursor(); cur.execute('SELECT name FROM sqlite_master WHERE type=\"table\" ORDER BY name'); print('Tables:'); [print(' -', r[0]) for r in cur.fetchall()]; con.close()"
```

### Count rows in file_registry

```powershell
python -c "import sqlite3; con=sqlite3.connect('file_registry.db'); cur=con.cursor(); cur.execute('SELECT COUNT(*) FROM file_registry'); print('file_registry rows:', cur.fetchone()[0]); con.close()"
```

### View sample file metadata (first 3 files)

```powershell
python -c "import sqlite3; con=sqlite3.connect('file_registry.db'); cur=con.cursor(); cur.execute('SELECT file_path, encoding, line_count FROM file_registry LIMIT 3'); print('Sample files:'); [print(f'  {r[0]} | {r[1]} | {r[2]} lines') for r in cur.fetchall()]; con.close()"
```

### Count cross-file dependencies detected

```powershell
python -c "import sqlite3; con=sqlite3.connect('file_registry.db'); cur=con.cursor(); cur.execute('SELECT ref_type, COUNT(*) FROM cross_file_deps GROUP BY ref_type'); print('Cross-file deps:'); [print(f'  {r[0]}: {r[1]}') for r in cur.fetchall()]; con.close()"
```

### View data lineage edges (first 5)

```powershell
python -c "import sqlite3; con=sqlite3.connect('file_registry.db'); cur=con.cursor(); cur.execute('SELECT lineage_type, source_dataset, target_dataset FROM data_lineage LIMIT 5'); print('Data lineage sample:'); [print(f'  {r[0]}: {r[1]} -> {r[2]}') for r in cur.fetchall()]; con.close()"
```

---

## 2. Inspect schema (useful for debugging)

```powershell
python -c "import sqlite3; con=sqlite3.connect('file_registry.db'); cur=con.cursor(); cur.execute('SELECT sql FROM sqlite_master WHERE type=\"table\" AND name=\"file_registry\"'); print(cur.fetchone()[0]); con.close()"
```
