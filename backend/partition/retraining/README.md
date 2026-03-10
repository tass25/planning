# Continuous Learning — `partition/retraining/`

Post-deployment quality monitoring and KB feedback loop.

## Modules

| Module | Purpose |
|---|---|
| `feedback_ingestion.py` | Accepts corrections, cross-verifies via LLM, upserts accepted pairs to LanceDB KB |
| `quality_monitor.py` | Computes success_rate, partial_rate, avg_confidence over last N conversions; emits alerts |
| `retrain_trigger.py` | Evaluates 4 conditions that trigger retraining: KB growth, ECE, consecutive failures, KB gaps |

## Retraining Trigger Conditions

1. **KB Growth** — ≥ 500 new verified examples since last training
2. **ECE Drift** — Calibration ECE > 0.12 on held-out 20%
3. **Consecutive Failures** — success_rate < 0.70 for 2+ consecutive batches
4. **KB Gap** — Single failure mode accounts for > 40% of PARTIAL conversions

## Usage

```python
from partition.retraining.quality_monitor import ConversionQualityMonitor
from partition.retraining.retrain_trigger import RetrainTrigger

monitor = ConversionQualityMonitor(duckdb_conn)
metrics = monitor.evaluate()

trigger = RetrainTrigger(duckdb_conn)
decision = trigger.evaluate()
if decision.should_retrain:
    print(f"Retrain needed: {decision.trigger_reason}")
```
