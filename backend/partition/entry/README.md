# L2-A Entry Layer

File discovery, analysis, cross-file dependency resolution, registry persistence, and data lineage extraction.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 1 | `FileAnalysisAgent` | `file_analysis_agent.py` | Scan `.sas` files, detect encoding (chardet), compute SHA-256 hashes |
| 2 | `CrossFileDependencyResolver` | `cross_file_dep_resolver.py` | Resolve `%INCLUDE`, `LIBNAME`, `&macro` references across files |
| 3 | `RegistryWriterAgent` | `registry_writer_agent.py` | Persist `FileMetadata` to SQLite `file_registry` table (dedup by content_hash) |
| 4 | `DataLineageExtractor` | `data_lineage_extractor.py` | Track dataset-level read/write lineage (SET, MERGE, FROM, DATA, CREATE TABLE) |

## Architecture

```
Input: list of .sas file paths / directory
        |
        v
  FileAnalysisAgent (#1)
    -> Recursive scan, encoding detection (chardet), SHA-256
    -> Produces list[FileMetadata]
        |
        v
  CrossFileDependencyResolver (#2)
    -> Regex-based %INCLUDE / LIBNAME / &var resolution
    -> Writes to SQLite cross_file_deps table
        |
        v
  RegistryWriterAgent (#3)
    -> Upserts FileMetadata into file_registry
    -> Content-hash deduplication
        |
        v
  DataLineageExtractor (#4)
    -> Table-level lineage (reads/writes per block)
    -> Writes to data_lineage table
```

## Key Features

- **Encoding detection** via `chardet` — handles legacy EBCDIC/CP1252 SAS files
- **SHA-256 content hashing** — enables dedup and change detection
- **Balanced block pre-validation** — regex check for DATA/PROC/RUN/QUIT balance
- **Cross-file resolution** — maps `%INCLUDE 'path'` to actual file system paths

## Dependencies

`chardet`, `hashlib`, `re`, `pathlib`, `json`, `sqlalchemy` (via `sqlite_manager`), `structlog`
