"""
SAS PROC REG with STEPWISE selection translated to Python/pandas.

Translation Notes:
- SAS PROC REG SELECTION=STEPWISE uses F-statistics with p-value thresholds (SLE/SLS).
  Default thresholds: SLE (entry) = 0.15, SLS (removal) = 0.15.
- This translation uses statsmodels OLS with p-value-based stepwise selection.
- Data is assumed to be loaded from staging.joined_master (SAS table).
"""

import pandas as pd
import statsmodels.api as sm


def stepwise_selection(X, y, sle=0.15, sls=0.15):
    """
    Perform stepwise selection using p-value thresholds.
    
    This replicates SAS PROC REG SELECTION=STEPWISE behavior:
    - Forward step: add variable with lowest p-value if p <= SLE
    - Backward step: remove variable with highest p-value if p >= SLS
    - Only runs backward step after a successful forward addition
    
    Parameters:
        X: DataFrame of predictor variables
        y: Series of target variable
        sle: Significance level for entry (default 0.15)
        sls: Significance level for stay (default 0.15)
    
    Returns:
        List of selected variable names
    """
    included = []
    while True:
        changed = False
        
        # Forward step: try adding each excluded variable
        excluded = [c for c in X.columns if c not in included]
        pvals = {}
        for col in excluded:
            model = sm.OLS(y, sm.add_constant(X[included + [col]])).fit()
            pvals[col] = model.pvalues[col]
        
        best = min(pvals, key=pvals.get) if pvals else None
        if best and pvals[best] <= sle:
            included.append(best)
            changed = True
        
        # Backward step: ONLY run after a successful forward addition
        # This prevents infinite oscillation (SAS resolves in single pass per iteration)
        if changed and included:
            model = sm.OLS(y, sm.add_constant(X[included])).fit()
            worst = model.pvalues[included].idxmax()
            if model.pvalues[worst] >= sls:
                included.remove(worst)
                # Do NOT set changed=True here
        
        if not changed:
            break
    
    return included


# ---------------------------------------------------------------------------
# Load data (equivalent to SAS DATA=staging.joined_master)
# ---------------------------------------------------------------------------
# Replace this with your actual data loading logic
# Example: df = pd.read_parquet('path/to/joined_master.parquet')
try:
    df = pd.read_parquet('staging/joined_master.parquet')
except FileNotFoundError:
    # Fallback for CSV or demonstrate with sample data structure
    try:
        df = pd.read_csv('staging/joined_master.csv')
    except FileNotFoundError:
        raise FileNotFoundError(
            "Could not find staging/joined_master.parquet or staging/joined_master.csv. "
            "Please ensure the data file exists or update the loading path."
        )

# ---------------------------------------------------------------------------
# Prepare data for modeling
# ---------------------------------------------------------------------------
# Define target and predictors
target = 'total_balance'
predictors = ['region_code', 'manager_id']

# Verify required columns exist
missing_cols = [c for c in [target] + predictors if c not in df.columns]
if missing_cols:
    raise ValueError(f"Required columns not found in data: {missing_cols}")

# Drop rows with missing values in relevant columns (SAS uses listwise deletion for REG)
model_data = df[[target] + predictors].dropna()

if model_data.empty:
    raise ValueError("No valid observations after removing missing values.")

X = model_data[predictors]
y = model_data[target]

# ---------------------------------------------------------------------------
# Stepwise Selection (equivalent to SELECTION=STEPWISE)
# ---------------------------------------------------------------------------
selected_vars = stepwise_selection(X, y, sle=0.15, sls=0.15)

print(f"Stepwise Selection Results:")
print(f"  Selected predictors: {selected_vars}")

# ---------------------------------------------------------------------------
# Fit Final Model with Selected Variables
# ---------------------------------------------------------------------------
if selected_vars:
    X_final = sm.add_constant(X[selected_vars])
    final_model = sm.OLS(y, X_final).fit()
    
    print(f"\n{'='*60}")
    print("Predictive Model for Account Value")
    print(f"{'='*60}")
    print(final_model.summary())
else:
    print("Warning: No variables were selected by stepwise procedure.")
    final_model = None

# ---------------------------------------------------------------------------
# Optional: Save model results or predictions
# ---------------------------------------------------------------------------
# final_model can be used for predictions:
# predictions = final_model.predict(sm.add_constant(X_test[selected_vars]))
