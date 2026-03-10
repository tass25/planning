# Week 4: L2-D — Complexity & Strategy + Model Training

> **Priority**: P0 (Core infrastructure)  
> **Branch**: `week-04`  
> **Layer**: L2-D  
> **Agents to build**: ComplexityAgent (#8), StrategyAgent (#9)  
> **Prerequisite**: Week 3–4 complete (PartitionIR objects available with raw_code)  
> **Status**: ✅ COMPLETE — see [week-04Done.md](week-04Done.md)  
> **Post-consolidation (Week 13)**: ComplexityAgent + StrategyAgent consolidated into `RiskRouter`.  

---

## 🎯 Goal

Build the complexity analysis and strategy routing system. ComplexityAgent extracts 5 features from each code block, StrategyAgent uses a trained Logistic Regression (with Platt scaling) to classify risk level and assign a partition strategy. ECE on held-out 20% must be < 0.08.

---

## Tasks

### Task 1: ComplexityAgent (#8)

**File**: `partition/complexity/complexity_agent.py`

**Inputs**: `PartitionIR`  
**Outputs**: Updated `PartitionIR` with `complexity_score` and `ComplexityMetadata`

**5 Features**:

| # | Feature | Computation | Weight | Edge Case |
|---|---------|-------------|--------|-----------|
| 1 | Cyclomatic Complexity | `radon.complexity.cc_visit()`, normalized ÷20, clipped at 1.0 | 0.30 | Cap at 20 for outliers |
| 2 | Nesting Depth | Max `%IF/%DO` nesting from `control_depth`, normalized ÷10 | 0.25 | Macro-injected nesting counts +2 |
| 3 | Macro Density | `macro_call_count / total_lines`, log-scaled | 0.20 | Log scale prevents extreme outliers |
| 4 | Cross-file Deps | Count of LIBNAME/FILENAME/%INCLUDE refs | 0.15 | Circular deps → HIGH auto-override |
| 5 | SQL Complexity | JOIN count + nested SELECT depth, normalized | 0.10 | PROC SQL only; else 0 |

**Implementation**:

```python
import re
import math
from partition.base_agent import BaseAgent

class ComplexityAgent(BaseAgent):
    agent_name = "ComplexityAgent"

    # Feature weights (from cahier)
    WEIGHTS = [0.30, 0.25, 0.20, 0.15, 0.10]

    async def process(self, partition: PartitionIR) -> PartitionIR:
        code = partition.raw_code

        # Feature 1: Cyclomatic complexity (via radon)
        f1 = self._cyclomatic(code)

        # Feature 2: Nesting depth
        f2 = self._nesting_depth(partition)

        # Feature 3: Macro density
        f3 = self._macro_density(code)

        # Feature 4: Cross-file dependencies
        f4 = self._cross_file_deps(partition)

        # Feature 5: SQL complexity
        f5 = self._sql_complexity(code, partition)

        features = [f1, f2, f3, f4, f5]
        composite = sum(w * f for w, f in zip(self.WEIGHTS, features))
        composite = max(0.0, min(1.0, composite))  # clamp to [0, 1]

        partition.complexity_score = composite
        self.logger.info("complexity_computed",
            partition_id=str(partition.partition_id),
            score=composite,
            features=features)

        return partition

    def _cyclomatic(self, code: str) -> float:
        """Cyclomatic complexity via radon, normalized ÷20."""
        try:
            from radon.complexity import cc_visit
            results = cc_visit(code)
            if results:
                max_cc = max(r.complexity for r in results)
                return min(max_cc / 20.0, 1.0)
        except Exception:
            pass
        # Fallback: count decision points manually
        decisions = len(re.findall(
            r'\b(IF|ELSE IF|WHEN|%IF|%ELSE)\b', code, re.IGNORECASE
        ))
        return min(decisions / 20.0, 1.0)

    def _nesting_depth(self, partition: PartitionIR) -> float:
        """Max nesting depth, normalized ÷10."""
        depth = partition.control_depth
        if partition.has_macros:
            depth += 2  # macro-injected nesting penalty
        return min(depth / 10.0, 1.0)

    def _macro_density(self, code: str) -> float:
        """Macro calls / total lines, log-scaled."""
        lines = max(code.count('\n') + 1, 1)
        macro_calls = len(re.findall(r'%\w+\s*\(', code, re.IGNORECASE))
        density = macro_calls / lines
        return min(math.log1p(density * 10) / math.log1p(10), 1.0)

    def _cross_file_deps(self, partition: PartitionIR) -> float:
        """Count of cross-file references, normalized."""
        count = len(partition.dependency_refs)
        return min(count / 10.0, 1.0)

    def _sql_complexity(self, code: str, partition: PartitionIR) -> float:
        """JOIN count + nested SELECT depth for SQL blocks."""
        if partition.partition_type.value != "SQL_BLOCK":
            return 0.0
        joins = len(re.findall(r'\bJOIN\b', code, re.IGNORECASE))
        selects = len(re.findall(r'\bSELECT\b', code, re.IGNORECASE))
        nested_depth = max(0, selects - 1)  # first SELECT is the main query
        raw = (joins + nested_depth) / 10.0
        return min(raw, 1.0)
```

**Install radon**:
```bash
pip install radon
```

---

### Task 2: Training Data Generation

**File**: `scripts/generate_training_data.py`

**What**: Generate 500 labeled training examples from the gold standard corpus. Each annotated block becomes one training row with features + manually assigned `risk_level`.

**Format** (`benchmark/complexity_training.csv`):
```csv
partition_id,cyclomatic,nesting_depth,macro_density,cross_file_deps,sql_complexity,risk_level
uuid-1,0.15,0.10,0.00,0.00,0.00,LOW
uuid-2,0.45,0.30,0.20,0.10,0.00,MODERATE
uuid-3,0.85,0.60,0.50,0.40,0.30,HIGH
```

**Labeling guidelines**:

| Risk Level | Criteria |
|------------|----------|
| **LOW** | Simple DATA step, no macros, no cross-file deps, < 50 lines |
| **MODERATE** | Has macros OR moderate nesting OR PROC with options |
| **HIGH** | Nested macros + cross-file deps, OR complex PROC SQL, OR MERGE with BY |
| **UNCERTAIN** | Ambiguous — could go either way. Use sparingly (< 10% of labels) |

**Approach to reach 500 examples**:
- 721 blocks from gold standard → 721 rows directly
- Augment with synthetic examples: vary features systematically (remaining to reach ~1000)
- Ensure class balance: ~35% LOW, ~35% MODERATE, ~25% HIGH, ~5% UNCERTAIN

```python
import pandas as pd
import numpy as np

def generate_synthetic_training(n_synthetic=350):
    """Generate synthetic training rows with known risk levels."""
    rows = []
    for _ in range(n_synthetic):
        risk = np.random.choice(
            ["LOW", "MODERATE", "HIGH", "UNCERTAIN"],
            p=[0.35, 0.35, 0.25, 0.05]
        )
        if risk == "LOW":
            features = np.random.uniform(0.0, 0.35, size=5)
        elif risk == "MODERATE":
            features = np.random.uniform(0.20, 0.70, size=5)
        elif risk == "HIGH":
            features = np.random.uniform(0.50, 1.0, size=5)
        else:  # UNCERTAIN
            features = np.random.uniform(0.30, 0.70, size=5)

        rows.append({
            "cyclomatic": features[0],
            "nesting_depth": features[1],
            "macro_density": features[2],
            "cross_file_deps": features[3],
            "sql_complexity": features[4],
            "risk_level": risk,
        })

    return pd.DataFrame(rows)
```

---

### Task 3: StrategyAgent (#9) — Training Pipeline

**File**: `partition/complexity/strategy_agent.py`

**Training script**: `scripts/train_complexity_model.py`

```python
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score
import joblib

def train_model(csv_path="benchmark/complexity_training.csv",
                output_path="models/complexity_model.pkl"):
    # Load
    df = pd.read_csv(csv_path)
    feature_cols = ["cyclomatic", "nesting_depth", "macro_density",
                    "cross_file_deps", "sql_complexity"]
    X = df[feature_cols].values
    y = df["risk_level"].values

    # Split 80/20
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # Train base LR
    base_lr = LogisticRegression(
        multi_class='multinomial',
        solver='lbfgs',
        max_iter=1000,
        random_state=42
    )

    # Platt scaling via CalibratedClassifierCV
    calibrated = CalibratedClassifierCV(
        estimator=base_lr,
        method='sigmoid',  # Platt scaling
        cv=5
    )
    calibrated.fit(X_train, y_train)

    # Evaluate
    y_pred = calibrated.predict(X_test)
    y_proba = calibrated.predict_proba(X_test)

    print(classification_report(y_test, y_pred))
    print(f"Macro F1: {f1_score(y_test, y_pred, average='macro'):.3f}")

    # Compute ECE
    ece = compute_ece(y_test, y_pred, y_proba, n_bins=10)
    print(f"ECE: {ece:.4f} (target < 0.08)")

    # Save
    joblib.dump(calibrated, output_path)
    print(f"Model saved to {output_path}")

    return ece


def compute_ece(y_true, y_pred, y_proba, n_bins=10):
    """Expected Calibration Error."""
    confidences = np.max(y_proba, axis=1)
    accuracies = (y_pred == y_true).astype(float)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (confidences > bin_boundaries[i]) & (confidences <= bin_boundaries[i+1])
        if mask.sum() > 0:
            bin_acc = accuracies[mask].mean()
            bin_conf = confidences[mask].mean()
            ece += mask.sum() * abs(bin_acc - bin_conf)
    return ece / len(y_true)
```

---

### Task 4: StrategyAgent (#9) — Inference

**File**: `partition/complexity/strategy_agent.py`

```python
import joblib
import numpy as np
from partition.base_agent import BaseAgent
from partition.models.enums import RiskLevel, PartitionStrategy

class StrategyAgent(BaseAgent):
    agent_name = "StrategyAgent"

    # Risk level thresholds
    SCORE_RANGES = {
        RiskLevel.LOW: (0.00, 0.35),
        RiskLevel.MODERATE: (0.35, 0.68),
        RiskLevel.HIGH: (0.68, 1.00),
    }

    def __init__(self, model_path="models/complexity_model.pkl", trace_id=None):
        super().__init__(trace_id)
        self.model = joblib.load(model_path)

    async def process(self, partition: PartitionIR) -> PartitionIR:
        features = np.array([[
            partition.complexity_score,  # will be replaced by 5 raw features
            # Actually use the 5 individual features:
        ]])

        # Extract 5 features from partition metadata
        features = self._extract_features(partition)

        # Predict
        risk_pred = self.model.predict(features)[0]
        proba = self.model.predict_proba(features)[0]
        confidence = float(np.max(proba))

        # Map to RiskLevel
        risk_level = RiskLevel(risk_pred)

        # UNCERTAIN override: if calibration confidence < 0.65
        if confidence < 0.65:
            risk_level = RiskLevel.UNCERTAIN

        # Circular dep override → HIGH
        if any("circular" in ref.lower() for ref in partition.dependency_refs):
            risk_level = RiskLevel.HIGH

        # Determine partition strategy
        strategy = self._determine_strategy(partition, risk_level)

        # Update partition
        partition.risk_level = risk_level
        partition.calibration_confidence = confidence
        partition.strategy = strategy

        self.logger.info("strategy_assigned",
            partition_id=str(partition.partition_id),
            risk=risk_level.value,
            confidence=confidence,
            strategy=strategy.value)

        return partition

    def _extract_features(self, p: PartitionIR) -> np.ndarray:
        """Extract the 5 features as used in training."""
        # Note: ComplexityAgent should have stored these
        # For now, recompute from partition metadata
        from partition.complexity.complexity_agent import ComplexityAgent
        agent = ComplexityAgent.__new__(ComplexityAgent)
        f1 = agent._cyclomatic(p.raw_code)
        f2 = agent._nesting_depth(p)
        f3 = agent._macro_density(p.raw_code)
        f4 = agent._cross_file_deps(p)
        f5 = agent._sql_complexity(p.raw_code, p)
        return np.array([[f1, f2, f3, f4, f5]])

    def _determine_strategy(self, p: PartitionIR, risk: RiskLevel) -> PartitionStrategy:
        score = p.complexity_score
        if risk == RiskLevel.UNCERTAIN:
            return PartitionStrategy.HUMAN_REVIEW
        if score < 0.35 and not p.has_macros and len(p.dependency_refs) < 3:
            return PartitionStrategy.FLAT_PARTITION
        if p.has_macros or 0.35 <= score <= 0.68:
            return PartitionStrategy.MACRO_AWARE
        if len(p.dependency_refs) > 3 or 0.50 <= score <= 0.68:
            return PartitionStrategy.DEPENDENCY_PRESERVING
        if score > 0.68 or p.has_nested_sql:
            return PartitionStrategy.STRUCTURAL_GROUPING
        return PartitionStrategy.FLAT_PARTITION
```

---

### Task 5: Reliability Diagram

**File**: `scripts/plot_reliability_diagram.py`

For the defense — visual proof that calibration is working:

```python
import matplotlib.pyplot as plt
import numpy as np

def plot_reliability_diagram(y_true, y_proba, y_pred, n_bins=10,
                             save_path="docs/reliability_diagram.png"):
    confidences = np.max(y_proba, axis=1)
    accuracies = (y_pred == y_true).astype(float)

    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_accs = []
    bin_confs = []
    bin_counts = []

    for i in range(n_bins):
        mask = (confidences > bin_edges[i]) & (confidences <= bin_edges[i+1])
        if mask.sum() > 0:
            bin_accs.append(accuracies[mask].mean())
            bin_confs.append(confidences[mask].mean())
            bin_counts.append(mask.sum())
        else:
            bin_accs.append(0)
            bin_confs.append((bin_edges[i] + bin_edges[i+1]) / 2)
            bin_counts.append(0)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(bin_confs, bin_accs, width=0.08, alpha=0.6, label="Model")
    ax.plot([0, 1], [0, 1], 'r--', label="Perfect calibration")
    ax.set_xlabel("Mean Predicted Confidence")
    ax.set_ylabel("Actual Accuracy")
    ax.set_title("Reliability Diagram (Platt-Calibrated LR)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(save_path, dpi=150)
    print(f"Saved to {save_path}")
```

---

### Task 6: DuckDB Calibration Log

**File**: `partition/db/duckdb_manager.py` (start this file — it grows over weeks)

```python
import duckdb

def init_calibration_log(db_path="analytics.duckdb"):
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS calibration_log (
            log_id VARCHAR PRIMARY KEY,
            ece_score DOUBLE,
            n_samples INTEGER,
            n_train INTEGER,
            model_version VARCHAR,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    con.close()

def log_calibration(db_path, log_id, ece, n_samples, n_train, version):
    con = duckdb.connect(db_path)
    con.execute("""
        INSERT INTO calibration_log VALUES (?, ?, ?, ?, ?, NOW())
    """, [log_id, ece, n_samples, n_train, version])
    con.close()
```

---

## Checklist — End of Week 4

- [ ] `partition/complexity/complexity_agent.py` — ComplexityAgent (#8) with 5 features
- [ ] `partition/complexity/strategy_agent.py` — StrategyAgent (#9) with LR + Platt scaling
- [ ] `scripts/train_complexity_model.py` — training pipeline with ECE computation
- [ ] `scripts/generate_training_data.py` — 500 labeled examples (150 real + 350 synthetic)
- [ ] `benchmark/complexity_training.csv` — training dataset
- [ ] `models/complexity_model.pkl` — trained model file
- [ ] `scripts/plot_reliability_diagram.py` — visual calibration check
- [ ] `partition/db/duckdb_manager.py` — calibration_log table + insert
- [ ] ECE < 0.08 on held-out 20%
- [ ] Macro F1 ≥ 0.75
- [ ] Classification accuracy ≥ 0.80
- [ ] Reliability diagram saved to `docs/`
- [ ] 5+ tests in `tests/test_complexity.py`
- [ ] CI guard: `tests/regression/test_ece.py`
- [ ] Git: `week-04` branch, merged to `main`

---

## Evaluation Metrics for This Week

| Metric | Target | How to Measure |
|--------|--------|----------------|
| ECE | < 0.08 | Held-out 20% reliability diagram |
| Classification accuracy | ≥ 0.80 | Held-out 20% |
| Macro F1 | ≥ 0.75 | `f1_score(average='macro')` |
| HUMAN_REVIEW precision | ≥ 0.70 | Manual audit of 20 HUMAN_REVIEW blocks |
| Strategy accuracy | ≥ 0.80 | Compare to gold standard labels |

---

## Dependencies Added This Week

| Package | Version | Purpose |
|---------|---------|---------|
| radon | ≥ 6.0 | Cyclomatic complexity |
| scikit-learn | ≥ 1.3 | LogisticRegression + CalibratedClassifierCV |
| joblib | ≥ 1.3 | Model serialization |
| matplotlib | ≥ 3.7 | Reliability diagram |
| duckdb | ≥ 0.9 | Calibration log |

---

> *Week 4 Complete → You have: 9 agents, complexity scoring, calibrated risk classification, ECE-validated strategy routing. P0 is done! Next: RAPTOR clustering (Week 5–6, P1).*
