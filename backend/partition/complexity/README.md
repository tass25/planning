# L2-D Complexity & Strategy Layer

Risk scoring via calibrated machine learning + strategy routing for conversion approach.

## Agents

| # | Agent | File | Purpose |
|---|-------|------|---------|
| 11 | `ComplexityAgent` | `complexity_agent.py` | LogReg + Platt-calibrated classifier; ECE = 0.06 |
| 12 | `StrategyAgent` | `strategy_agent.py` | Risk x Type routing table → conversion strategy |

## Files

| File | Description |
|------|-------------|
| `features.py` | `BlockFeatures` frozen dataclass — 6 features: `line_count_norm`, `nesting_depth_norm`, `macro_pct`, `has_call_execute`, `type_weight`, `is_ambiguous` |
| `complexity_agent.py` | Trains on gold corpus (~580 samples); Platt scaling via `CalibratedClassifierCV`; rule-based fallback |
| `strategy_agent.py` | Pure lookup table: `RiskLevel × PartitionType` → `PartitionStrategy` (5 strategies) |

## Architecture

```
list[PartitionIR] (from Chunking/RAPTOR)
        |
        v
  ComplexityAgent (#11)
    -> Extract 6 features per partition (BlockFeatures)
    -> Train LogReg on gold_standard corpus
    -> Platt calibration (CalibratedClassifierCV)
    -> Assign RiskLevel: LOW / MODERATE / HIGH / CRITICAL
    -> ECE target < 0.08 (current: 0.06)
        |
        v  list[PartitionIR] with risk_level set
  StrategyAgent (#12)
    -> RiskLevel x PartitionType -> PartitionStrategy
    -> 5 strategies:
       FLAT_PARTITION | MACRO_AWARE | DEPENDENCY_PRESERVING |
       STRUCTURAL_GROUPING | HUMAN_REVIEW
        |
        v  list[PartitionIR] with strategy set
  (downstream: Persistence -> Index)
```

## Strategy Routing Table

| Risk \ Type | DATA_STEP | PROC | MACRO | CALL_EXECUTE |
|-------------|-----------|------|-------|-------------|
| LOW | FLAT_PARTITION | FLAT_PARTITION | MACRO_AWARE | MACRO_AWARE |
| MODERATE | MACRO_AWARE | MACRO_AWARE | DEPENDENCY_PRESERVING | DEPENDENCY_PRESERVING |
| HIGH | DEPENDENCY_PRESERVING | STRUCTURAL_GROUPING | STRUCTURAL_GROUPING | HUMAN_REVIEW |
| CRITICAL | HUMAN_REVIEW | HUMAN_REVIEW | HUMAN_REVIEW | HUMAN_REVIEW |

## Key Features

- **Calibrated probabilities** — Platt scaling ensures ECE < 0.08 (not just accuracy)
- **Gold-corpus training** — Uses 50 annotated files (~580 blocks) for supervised training
- **Rule-based fallback** — If gold corpus unavailable, heuristic assignment works
- **Zero LLM calls** — Entirely ML/heuristic, no API cost at this layer

## Dependencies

`numpy`, `scikit-learn` (LogisticRegression, CalibratedClassifierCV, LabelEncoder), `re`, `structlog`
