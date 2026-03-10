"""Week 4 Visualization: Complexity Agent + Calibration

Shows:
- Feature importance from LogReg weights
- Calibration plot (predicted prob vs true prob)
- ECE score visualization
- Risk level distribution

Run from repo root on main:
    python planning/week04viz.py
"""

import sys
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError:
    print("ERROR: Install matplotlib + numpy:")
    print("  pip install matplotlib numpy")
    sys.exit(1)

print("=" * 70)
print("WEEK 4: Complexity Agent + Calibration")
print("=" * 70)

# ── Data from week04Done.md ────────────────────────────────────────────────────
# After fit(gold_dir, test_size=0.20, seed=42):
# train_acc ~86%, test_acc ~73%, ECE ~0.06

train_acc = 86.0
test_acc = 73.0
ece = 0.06
n_train = 576
n_test = 145
target_ece = 0.08

# Feature names + mock coefficients (real coefficients would come from the trained model)
# For visualization, we'll use representative values
features = [
    'line_count_norm',
    'nesting_depth_norm',
    'macro_pct',
    'has_call_execute',
    'type_weight',
    'is_ambiguous'
]
# Mock LogReg coefficients (would extract from actual model.coef_)
coef_high = np.array([0.45, 0.62, 0.38, 1.2, 0.55, 0.48])
coef_mod = np.array([0.22, 0.31, 0.19, 0.0, 0.28, 0.24])

# Risk level distribution (from gold corpus tier mapping)
risk_dist = {'LOW': 350, 'MODERATE': 220, 'HIGH': 151}

# ── 1. Feature Importance (LogReg Coefficients) ────────────────────────────────
fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(14, 10))

x_pos = np.arange(len(features))
ax1.barh(x_pos, coef_high, color='coral', alpha=0.7, label='HIGH risk coef')
ax1.barh(x_pos, coef_mod, color='lightblue', alpha=0.7, label='MODERATE coef')
ax1.set_yticks(x_pos)
ax1.set_yticklabels(features, fontsize=9)
ax1.set_xlabel('Coefficient Weight', fontsize=10)
ax1.set_title('Week 4: Feature Importance (LogReg Coefficients)', fontsize=11, fontweight='bold')
ax1.legend()
ax1.grid(axis='x', alpha=0.3)

print("\nFeature importance (mock coefficients for HIGH risk):")
for feat, coef in zip(features, coef_high):
    print(f"   {feat:20s}: {coef:+.2f}")

# ── 2. Calibration Curve (Reliability Diagram) ─────────────────────────────────
# Mock calibration data (ideal: predicted prob == true prob)
predicted_probs = np.linspace(0, 1, 10)
true_probs = predicted_probs + np.random.normal(0, 0.04, 10)  # Small noise
true_probs = np.clip(true_probs, 0, 1)

ax2.plot([0, 1], [0, 1], 'k--', label='Perfect calibration', linewidth=1.5)
ax2.plot(predicted_probs, true_probs, 'o-', color='steelblue', 
         linewidth=2, markersize=8, label='Platt-calibrated LR')
ax2.set_xlabel('Predicted Probability', fontsize=10)
ax2.set_ylabel('True Probability', fontsize=10)
ax2.set_title('Week 4: Calibration Plot (ECE = 0.06)', fontsize=11, fontweight='bold')
ax2.legend()
ax2.grid(True, alpha=0.3)
ax2.set_xlim(-0.05, 1.05)
ax2.set_ylim(-0.05, 1.05)

# ── 3. ECE Visualization ───────────────────────────────────────────────────────
ece_bins = ['Bin 1', 'Bin 2', 'Bin 3', 'Bin 4', 'Bin 5', 
            'Bin 6', 'Bin 7', 'Bin 8', 'Bin 9', 'Bin 10']
ece_errors = np.random.uniform(0.02, 0.08, 10)  # Mock per-bin errors
ece_errors[0] = 0.02  # First bin typically lower

ax3.bar(range(len(ece_bins)), ece_errors, color='lightcoral', alpha=0.8)
ax3.axhline(y=ece, color='red', linestyle='--', linewidth=2, label=f'ECE = {ece:.2f}')
ax3.axhline(y=target_ece, color='green', linestyle='--', linewidth=1.5, 
            label=f'Target < {target_ece:.2f}')
ax3.set_xlabel('Confidence Bin', fontsize=10)
ax3.set_ylabel('Calibration Error', fontsize=10)
ax3.set_title('Week 4: Expected Calibration Error (ECE)', fontsize=11, fontweight='bold')
ax3.set_xticks(range(len(ece_bins)))
ax3.set_xticklabels(ece_bins, rotation=45, ha='right', fontsize=8)
ax3.legend()
ax3.grid(axis='y', alpha=0.3)

print("\nCalibration metrics:")
print(f"   Train accuracy: {train_acc:.1f}%")
print(f"   Test accuracy: {test_acc:.1f}%")
print(f"   ECE: {ece:.2f} (target: < {target_ece:.2f}) {'✅' if ece < target_ece else '❌'}")
print(f"   Train samples: {n_train}")
print(f"   Test samples: {n_test}")

# ── 4. Risk Level Distribution ─────────────────────────────────────────────────
labels = list(risk_dist.keys())
sizes = list(risk_dist.values())
colors = ['lightgreen', 'lightyellow', 'lightcoral']
explode = (0.05, 0.05, 0.05)

ax4.pie(sizes, explode=explode, labels=labels, colors=colors, autopct='%1.1f%%',
        shadow=True, startangle=90, textprops={'fontsize': 10, 'fontweight': 'bold'})
ax4.set_title('Week 4: Risk Level Distribution\n(Gold Corpus Tier Mapping)', 
              fontsize=11, fontweight='bold')

print("\nRisk level distribution:")
for label, size in zip(labels, sizes):
    print(f"   {label:10s}: {size:3d} blocks ({size/sum(sizes)*100:.1f}%)")

plt.tight_layout()
plt.show()

print("\n✅ Week 4 visualization complete.")
print("   ComplexityAgent: LogReg + Platt calibration")
print(f"   ECE {ece:.2f} < target {target_ece:.2f} ✅")
