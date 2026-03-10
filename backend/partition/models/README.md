# Data Models

Pydantic data models and string enums shared across the pipeline.

## Files

| File | Description |
|------|-------------|
| `enums.py` | String enums: `PartitionType` (9), `RiskLevel` (4), `ConversionStatus` (4), `PartitionStrategy` (5) |
| `file_metadata.py` | `FileMetadata` — immutable scan result: path, encoding, SHA-256, size, line count, lark validation |
| `partition_ir.py` | `PartitionIR` — core pipeline unit: block_id, source_code, line range, risk, strategy, RAPTOR links, deps |
| `raptor_node.py` | `RAPTORNode` — tree node: level, summary, embedding (768-dim), child_ids, cluster_label, file_id |

## Enums

### PartitionType (9 values)
`DATA_STEP`, `PROC_SQL`, `PROC_SORT`, `PROC_MEANS`, `PROC_FREQ`, `PROC_PRINT`, `PROC_OTHER`, `MACRO_DEFINITION`, `GLOBAL_STATEMENT`

### RiskLevel (4 values)
`LOW`, `MODERATE`, `HIGH`, `CRITICAL`

### ConversionStatus (4 values)
`PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`

### PartitionStrategy (5 values)
`FLAT_PARTITION`, `MACRO_AWARE`, `DEPENDENCY_PRESERVING`, `STRUCTURAL_GROUPING`, `HUMAN_REVIEW`

## Dependencies

`pydantic` (BaseModel, Field), `enum` (str, Enum), `typing`
