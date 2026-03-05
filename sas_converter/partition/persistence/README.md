# L2-E Persistence Layer

SQLite-backed partition persistence with content-hash deduplication and batch writes.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 13 | `PersistenceAgent` | `persistence_agent.py` | Writes `PartitionIR` → SQLite with dedup and batch mode |

## Architecture

```
list[PartitionIR] (from Complexity Layer)
        |
        v
  PersistenceAgent (#13)
    -> Content-hash dedup (skip if hash exists in DB)
    -> Batch upsert to partition_ir table
    -> SQLAlchemy ORM via sqlite_manager
    -> Parquet fallback stub for >= 10k blocks
        |
        v
  SQLite file_registry.db (WAL mode)
    -> partition_ir table
    -> Joins to file_registry, cross_file_deps, data_lineage
```

## Key Features

- **Content-hash deduplication** — SHA-256 hash prevents duplicate partition writes
- **Batch writes** — Groups upserts for efficiency on large corpora
- **WAL journal mode** — Concurrent reads during writes
- **Parquet fallback** — Stub for scaling beyond 10k blocks (future)

## Dependencies

`structlog`, `sqlalchemy` (via `db/sqlite_manager`)
