# Week 4 Visualization: Complexity Agent Calibration

> Artifacts produced: Calibration metrics (stored in DuckDB when wired, or printed to console)

**What this week delivered:**
- `ComplexityAgent` (logistic regression + Platt calibration)
- `StrategyAgent` (risk-level routing)
- ECE = 0.06 < 0.08 target ✅

**Visualization: Calibration metrics**

The `ComplexityAgent.fit()` method returns a dict with these keys:
- `train_acc` — training accuracy
- `test_acc` — test accuracy
- `ece` — Expected Calibration Error
- `n_train`, `n_test` — sample counts

### If metrics were logged to DuckDB (Week 7 wiring):

```powershell
python -c "import duckdb; con=duckdb.connect('analytics.duckdb'); print(con.execute('SELECT * FROM calibration_log ORDER BY created_at DESC LIMIT 5').fetchall()); con.close()"
```

### If you want to run calibration manually and see metrics:

1. Switch to `main`:
   ```powershell
   git checkout main
   ```

2. Run a quick calibration test:
   ```powershell
   python -c "
from partition.complexity.complexity_agent import ComplexityAgent
agent = ComplexityAgent()
result = agent.fit('sas_converter/knowledge_base/gold_standard', test_size=0.20, seed=42)
print('Calibration results:')
for k,v in result.items():
    print(f'  {k}: {v}')
"
   ```

**Expected output:**
```
train_acc: ~0.86
test_acc: ~0.73
ece: ~0.06
n_train: 576
n_test: 145
```

---

## Inspect feature extraction on a sample partition

```powershell
python -c "
from partition.complexity.features import extract
from partition.models.partition_ir import PartitionIR
from partition.models.enums import PartitionType

# Mock partition
p = PartitionIR(
    partition_id='test_1',
    partition_type=PartitionType.DATA_STEP,
    raw_code='DATA out; SET in; x=x+1; RUN;',
    line_start=1,
    line_end=4,
    metadata={'nesting_depth': 0, 'is_ambiguous': False},
)
feats = extract(p)
print('Features:', feats)
"
```
