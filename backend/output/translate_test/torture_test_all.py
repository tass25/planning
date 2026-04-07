

# ======================================================================# Block 1: block_0
# ======================================================================


"""
SAS-to-Python Translation: Finance Data Migration Pipeline
Generated from ~150 lines of mixed Data Steps, Procedures, Macros, and Globals

Translation Notes:
- All imports at top
- Idiomatic pandas patterns used throughout
- No iterrows() - vectorized operations only
- PROC FORMAT translated as display-only (new column, not overwrite)
- MERGE with IN= translated using pd.merge(indicator=True)
- PROC REG STEPWISE uses statsmodels with p-value thresholds (SLE=0.15, SLS=0.15)
"""

import pandas as pd
import numpy as np
import re
import os
from datetime import datetime, date
import statsmodels.api as sm

# ============================================================================
# 1. CONFIGURATION & ENVIRONMENT SETUP
# ============================================================================

# SAS equivalent: %LET env = PRODUCTION;
env = "PRODUCTION"

# SAS equivalent: %LET process_date = %SYSFUNC(today(), date9.);
# Format: DDMMMYYYY (e.g., 01JAN2024)
process_date = date.today().strftime("%d%b%Y").upper()

# SAS equivalent: %LET threshold = 5000;
threshold = 5000

# File paths (SAS equivalent: LIBNAME and FILENAME)
RAW_SRC_PATH = "/data/raw/source_systems"
STAGING_PATH = "/data/staging/temp_storage"
FINAL_PATH = "/data/production/final_tables"
LOG_OUT_PATH = "/logs/migration_audit.txt"

# ============================================================================
# 2. MACRO DEFINITION: preprocess_finance_data(in_ds, out_ds)
# ============================================================================

def preprocess_finance_data(in_df, out_ds_path):
    """
    Translates SAS MACRO preprocess_finance_data:
    - UPCASE(STRIP(name)) → customer_name
    - COMPRESS(account_id, '-') → removes ONLY hyphens (2-arg form)
    - Conditional status assignment using np.select
    - Date arithmetic: today() - last_transaction_dt
    - PROC SORT: BY account_id DESCENDING days_since_active
    
    Args:
        in_df: Input DataFrame (already loaded from source)
        out_ds_path: Path to save output DataFrame
    
    Returns:
        DataFrame with preprocessing applied
    """
    df = in_df.copy()
    
    # SAS: customer_name = UPCASE(STRIP(name));
    df['customer_name'] = df['name'].str.strip().str.upper()
    
    # SAS: account_id = COMPRESS(account_id, '-');
    # IMPORTANT: 2-argument COMPRESS removes ONLY the listed character (hyphen)
    # NOT the default 1-argument behavior which removes all non-alphanumeric
    df['account_id'] = df['account_id'].str.replace('-', '', regex=False)
    
    # SAS: IF balance < 0 THEN DO; status = 'OVERDRAWN'; flag = 1; END;
    #       ELSE IF balance = 0 THEN status = 'EMPTY';
    #       ELSE status = 'ACTIVE';
    conditions = [
        df['balance'] < 0,
        df['balance'] == 0
    ]
    choices = ['OVERDRAWN', 'EMPTY']
    df['status'] = np.select(conditions, choices, default='ACTIVE')
    
    # Add flag column for OVERDRAWN accounts (SAS: flag = 1 when balance < 0)
    df['flag'] = (df['balance'] < 0).astype(int)
    
    # SAS: days_since_active = today() - last_transaction_dt;
    df['days_since_active'] = (pd.Timestamp.today() - pd.to_datetime(df['last_transaction_dt'])).dt.days
    
    # SAS: IF days_since_active > 365 THEN account_type = 'DORMANT';
    #       ELSE account_type = 'CURRENT';
    df['account_type'] = np.where(df['days_since_active'] > 365, 'DORMANT', 'CURRENT')
    
    # SAS: LABEL status = "Account Status Indicator"
    #       account_type = "Activity Classification"
    # Python: Add as column metadata/comments (pandas doesn't have LABEL statement)
    # Labels are preserved in the column name comments where applicable
    
    # Drop err_code (SAS: DROP=err_code - not created in Python version)
    # No err_code column was created, so nothing to drop
    
    # SAS PROC SORT: BY account_id descending days_since_active;
    # Translation: account_id ASCENDING, days_since_active DESCENDING
    df = df.sort_values(
        ['account_id', 'days_since_active'],
        ascending=[True, False]
    )
    
    # Save output (SAS equivalent: DATA &out_ds)
    df.to_parquet(out_ds_path, index=False)
    
    return df


def stepwise_selection(X, y, sle=0.15, sls=0.15):
    """
    Translates SAS: PROC REG; MODEL y = x1 x2 / SELECTION=STEPWISE;
    
    SAS PROC REG STEPWISE uses F-statistic p-value thresholds:
    - SLE (Significance Level for Entry) = 0.15 default
    - SLS (Significance Level for Stay) = 0.15 default
    
    Algorithm:
    1. Forward step: add variable with lowest p-value IF p <= SLE
    2. Backward step: remove variable with p >= SLS after each addition
    3. Repeat until convergence
    
    IMPORTANT: Uses p-values, NOT BIC/AIC (common mistake)
    
    Args:
        X: DataFrame of predictor variables
        y: Series of response variable
        sle: Significance level for entry (default 0.15)
        sls: Significance level for removal (default 0.15)
    
    Returns:
        List of selected column names
    """
    included = []
    
    while True:
        changed = False
        
        # ----- Forward step -----
        # Find p-values for all excluded variables
        excluded = [c for c in X.columns if c not in included]
        pvals = {}
        
        for col in excluded:
            # Fit model with candidate variable added
            predictors = included + [col]
            X_const = sm.add_constant(X[predictors])
            model = sm.OLS(y, X_const).fit()
            pvals[col] = model.pvalues[col]
        
        # Add variable with lowest p-value if below threshold
        if pvals:
            best = min(pvals, key=pvals.get)
            if pvals[best] <= sle:
                included.append(best)
                changed = True
        
        # ----- Backward step -----
        # After adding, check if any included variable should be removed
        if included:
            X_const = sm.add_constant(X[included])
            model = sm.OLS(y, X_const).fit()
            
            # Find variable with highest p-value among included
            pvalues = model.pvalues[included]
            worst = pvalues.idxmax()
            
            if pvalues[worst] >= sls:
                included.remove(worst)
                changed = True
        
        if not changed:
            break
    
    return included


# ============================================================================
# 3. PROCEDURE SQL BLOCK: LEFT JOIN with aggregation
# ============================================================================

def sql_join_and_aggregate(cleaned_accounts_df, region_map_df):
    """
    Translates SAS PROC SQL:
    - LEFT JOIN on region_code = code
    - WHERE balance > threshold
    - GROUP BY account_id, status, region, manager_id
    - SUM(a.balance) AS total_balance
    - ORDER BY total_balance DESC
    
    CRITICAL: Must preserve region_code and manager_id for PROC REG (downstream)
    """
    # Normalize column names for merge (SAS is case-insensitive, Python is NOT)
    region_map_norm = region_map_df.copy()
    region_map_norm.columns = region_map_norm.columns.str.lower()
    
    cleaned_norm = cleaned_accounts_df.copy()
    cleaned_norm.columns = cleaned_norm.columns.str.lower()
    
    # Merge (SAS: LEFT JOIN)
    merged = cleaned_norm.merge(
        region_map_norm,
        left_on='region_code',
        right_on='code',
        how='left',
        indicator=True  # Track merge status (equivalent to IN= variables)
    )
    
    # SAS: WHERE balance > &threshold
    merged = merged[merged['balance'] > threshold]
    
    # SAS: GROUP BY 1, 2, 3, 4 (account_id, status, region, manager_id)
    # Aggregate: SUM(a.balance) AS total_balance
    # dropna=False ensures NaN groups are preserved (SAS CLASS behavior)
    result = merged.groupby(
        ['account_id', 'status', 'region', 'manager_id'],
        dropna=False
    ).agg(
        total_balance=('balance', 'sum')
    ).reset_index()
    
    # SAS: ORDER BY total_balance DESC
    result = result.sort_values('total_balance', ascending=False)
    
    return result


# ============================================================================
# 4. DATA STEP WITH IN-LINE DATALINES
# ============================================================================

def create_manual_adjustments():
    """
    Translates SAS DATA step with DATALINES:
    INPUT Account_ID $ Adjustment_Amt Type $;
    DATALINES;
    ACC100 250.00 REBATE
    ACC205 -50.25 FEE
    ACC309 1000.00 BONUS
    ACC412 -15.00 CHARGE
    ;
    """
    data = {
        'Account_ID': ['ACC100', 'ACC205', 'ACC309', 'ACC412'],
        'Adjustment_Amt': [250.00, -50.25, 1000.00, -15.00],
        'Type': ['REBATE', 'FEE', 'BONUS', 'CHARGE']
    }
    
    return pd.DataFrame(data)


# ============================================================================
# 5. PROC MEANS: Summary statistics with CLASS
# ============================================================================

def proc_means_summary(df):
    """
    Translates SAS PROC MEANS:
    PROC MEANS DATA=staging.joined_master N MEAN STD MIN MAX;
        CLASS region status;
        VAR total_balance;
        OUTPUT OUT=work.summary_stats
            MEAN=avg_balance
            SUM=total_regional_val;
    
    CRITICAL RULES:
    - Single groupby().agg() call with ALL statistics (NOT separate merges)
    - dropna=False to preserve NaN groups (SAS CLASS includes missing)
    - NWAY is default pandas groupby behavior (full cross-classification only)
    """
    # SAS: CLASS region status - two classification variables
    # SAS: N MEAN STD MIN MAX - five statistics
    # SAS: OUTPUT OUT with renamed variables
    
    result = df.groupby(
        ['region', 'status'],
        dropna=False  # SAS CLASS includes missing values as a group
    ).agg(
        N=('total_balance', 'count'),
        avg_balance=('total_balance', 'mean'),
        STD=('total_balance', 'std'),
        MIN=('total_balance', 'min'),
        MAX=('total_balance', 'max'),
        total_regional_val=('total_balance', 'sum')
    ).reset_index()
    
    return result


# ============================================================================
# 6. PROC FORMAT: Value mapping (DISPLAY ONLY)
# ============================================================================

# SAS equivalent:
# PROC FORMAT;
#     VALUE $grade
#         'OVERDRAWN' = 'Red'
#         'ACTIVE'    = 'Green'
#         'DORMANT'   = 'Yellow'
#         OTHER       = 'Gray';
# RUN;

# IMPORTANT: SAS FORMAT is display-only, never modifies underlying data
# Create a NEW column, don't overwrite the original

GRADE_FORMAT = {
    'OVERDRAWN': 'Red',
    'ACTIVE': 'Green',
    'DORMANT': 'Yellow'
}

def apply_grade_format(df, source_col='status', target_col='status_color'):
    """
    Apply $GRADE format to a DataFrame column.
    Creates NEW column, preserves original.
    """
    df[target_col] = df[source_col].map(GRADE_FORMAT).fillna('Gray')
    return df


# ============================================================================
# 7. PROC REG: STEPWISE REGRESSION
# ============================================================================

def proc_reg_stepwise(df):
    """
    Translates SAS PROC REG with STEPWISE selection:
    PROC REG DATA=staging.joined_master;
        MODEL total_balance = region_code manager_id / SELECTION=STEPWISE;
        TITLE "Predictive Model for Account Value";
    
    CRITICAL:
    - Uses p-value thresholds (SLE=0.15, SLS=0.15), NOT BIC/AIC
    - Must preserve region_code column from upstream (used in MODEL)
    - Uses statsmodels OLS, not sklearn
    """
    # Prepare predictors - need region_code for the model
    # Note: If region_code is categorical, would need pd.get_dummies()
    # For numeric region_code, use as-is
    X = df[['region_code', 'manager_id']].copy()
    y = df['total_balance']
    
    # Drop rows with missing values in predictors or response
    valid_mask = X.notna().all(axis=1) & y.notna()
    X = X[valid_mask]
    y = y[valid_mask]
    
    # Forward/backward stepwise selection using p-values
    selected_vars = stepwise_selection(X, y, sle=0.15, sls=0.15)
    
    print(f"Predictive Model for Account Value")
    print(f"Selected variables: {selected_vars}")
    
    # Fit final model with selected variables
    if selected_vars:
        X_selected = sm.add_constant(X[selected_vars])
        final_model = sm.OLS(y, X_selected).fit()
        print(final_model.summary())
        return final_model, selected_vars
    else:
        print("No variables selected in stepwise procedure.")
        return None, []


# ============================================================================
# 8. PROC FREQ: Cross-tabulation
# ============================================================================

def proc_freq(df):
    """
    Translates SAS PROC FREQ:
    PROC FREQ DATA=final.monthly_report;
        TABLES region * status / NOCOL NOPERCENT;
    
    NOCOL = suppress column percentages
    NOPERCENT = suppress all percentages
    """
    # Cross-tabulation without percentages
    freq_table = pd.crosstab(
        df['region'],
        df['status'],
        dropna=False  # SAS CLASS/FREQ includes missing
    )
    
    return freq_table


# ============================================================================
# 9. PROC PRINT: Display data
# ============================================================================

def proc_print(df, n=10):
    """
    Translates SAS PROC PRINT:
    PROC PRINT DATA=work.summary_stats (OBS=10);
        TITLE "Top 10 Summary Statistics Preview";
    
    OBS=n limits output to first n rows
    """
    return df.head(n)


# ============================================================================
# 10. MAIN PIPELINE EXECUTION
# ============================================================================

def main():
    """
    Main execution pipeline that reproduces the SAS code logic.
    Loads data, processes it through all steps, and exports results.
    """
    
    # -------------------------------------------------------------------------
    # Step 6: Macro call (preprocess_finance_data)
    # SAS: %preprocess_finance_data(raw_src.daily_ledger, staging.cleaned_accounts);
    # -------------------------------------------------------------------------
    
    # Load source data (SAS: raw_src.daily_ledger)
    # In production, replace with actual data loading
    daily_ledger = pd.read_parquet(f"{RAW_SRC_PATH}/daily_ledger.parquet")
    
    # Apply preprocessing macro
    cleaned_accounts = preprocess_finance_data(
        daily_ledger,
        f"{STAGING_PATH}/cleaned_accounts.parquet"
    )
    
    # -------------------------------------------------------------------------
    # Step 3: PROC SQL - Join and aggregate
    # -------------------------------------------------------------------------
    
    # Load region mapping (SAS: raw_src.region_map)
    region_map = pd.read_parquet(f"{RAW_SRC_PATH}/region_map.parquet")
    
    joined_master = sql_join_and_aggregate(cleaned_accounts, region_map)
    
    # Save intermediate (SAS: staging.joined_master)
    joined_master.to_parquet(f"{STAGING_PATH}/joined_master.parquet", index=False)
    
    # -------------------------------------------------------------------------
    # Step 5: PROC MEANS
    # -------------------------------------------------------------------------
    
    summary_stats = proc_means_summary(joined_master)
    
    # Save (SAS: work.summary_stats)
    summary_stats.to_parquet(f"{STAGING_PATH}/summary_stats.parquet", index=False)
    
    # -------------------------------------------------------------------------
    # Step 8: PROC REG with STEPWISE
    # -------------------------------------------------------------------------
    
    # Need to add region_code to joined_master for PROC REG
    # (merged data should have region_code from cleaned_accounts)
    final_model, selected_vars = proc_reg_stepwise(joined_master)
    
    # -------------------------------------------------------------------------
    # Step 4: DATA step with DATALINES
    # -------------------------------------------------------------------------
    
    manual_adjustments = create_manual_adjustments()
    
    # -------------------------------------------------------------------------
    # Step 9: DATA step with MERGE
    # SAS: MERGE staging.joined_master (IN=a) work.manual_adjustments (IN=b);
    #      BY Account_ID;
    #      IF a;  (keep all primary records)
    #      IF b THEN total_balance = total_balance + Adjustment_Amt;
    # -------------------------------------------------------------------------
    
    # Normalize column names before merge (CRITICAL: SAS is case-insensitive)
    joined_master_norm = joined_master.copy()
    joined_master_norm.columns = joined_master_norm.columns.str.lower()
    
    manual_adj_norm = manual_adjustments.copy()
    manual_adj_norm.columns = manual_adj_norm.columns.str.lower()
    
    # SAS MERGE with IN= variables
    # IF a; keeps all records from primary (left) table
    # IF b; adds adjustment to records in both tables
    monthly_report = joined_master_norm.merge(
        manual_adj_norm,
        on='account_id',  # BY Account_ID (case-normalized)
        how='left',
        indicator=True  # Creates '_merge' column (equivalent to IN=)
    )
    
    # SAS: IF a; - keep all primary records (already done with how='left')
    # SAS: IF b THEN total_balance = total_balance + Adjustment_Amt;
    # Apply adjustment only where record exists in both (equivalent to IF b)
    monthly_report.loc[
        monthly_report['_merge'] == 'both',
        'total_balance'
    ] = (
        monthly_report.loc[
            monthly_report['_merge'] == 'both',
            'total_balance'
        ] + monthly_report.loc[
            monthly_report['_merge'] == 'both',
            'adjustment_amt'
        ]
    )
    
    # SAS: MONTH = "%SUBSTR(&process_date, 3, 3)";
    # Extract characters 3-5 from process_date (0-indexed: 2-5)
    monthly_report['MONTH'] = process_date[2:5]
    
    # SAS: YEAR = "%SUBSTR(&process_date, 6, 4)";
    # Extract characters 6-9 from process_date (0-indexed: 5-9)
    monthly_report['YEAR'] = process_date[5:9]
    
    # SAS: FORMAT status $grade.;
    # IMPORTANT: SAS FORMAT is display-only, never overwrites original data
    monthly_report = apply_grade_format(monthly_report, 'status', 'status_color')
    
    # -------------------------------------------------------------------------
    # Step 10: PROC EXPORT
    # -------------------------------------------------------------------------
    
    output_filename = f"/output/migration_validation_{process_date}.csv"
    monthly_report.to_csv(output_filename, index=False)
    
    # -------------------------------------------------------------------------
    # Step 11: PROC FREQ and PROC PRINT
    # -------------------------------------------------------------------------
    
    # PROC FREQ
    freq_results = proc_freq(monthly_report)
    print("\nPROC FREQ Results (region * status):")
    print(freq_results)
    
    # PROC PRINT (OBS=10)
    print("\nTop 10 Summary Statistics Preview:")
    top_10 = proc_print(summary_stats, n=10)
    print(top_10)
    
    # -------------------------------------------------------------------------
    # Cleanup step (SAS DATA _NULL_)
    # -------------------------------------------------------------------------
    
    cleanup_flag = 1
    if cleanup_flag == 1:
        timestamp = datetime.now().strftime("%d%b%Y %H:%M:%S").upper()
        log_message = f"MIGRATION PARTITIONING TEST COMPLETE: {timestamp}"
        print(log_message)
        
        # Write to log file
        with open(LOG_OUT_PATH, 'a') as f:
            f.write(f"{log_message}\n")
    
    return {
        'cleaned_accounts': cleaned_accounts,
        'joined_master': joined_master,
        'summary_stats': summary_stats,
        'monthly_report': monthly_report,
        'final_model': final_model
    }


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    results = main()
