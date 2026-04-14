"""
translation_minimax-m2.7_cloud.py

Model        : minimax-m2.7:cloud
Generated    : 2026-04-12T22:12:12.233924+00:00
Blocks       : 10
Success      : 10/10  (100%)
Z3 proved    : 3/10
Mean latency : 12.8s
Total tokens : 11,289
"""

# ============================================================================
# Block 01  1. RETAIN + BY-group FIRST./LAST.
# Risk       : HIGH
# SAS lines  : 12
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 16.2s
# Tokens     : 1225  (361 prompt + 864 completion)
# tok/s      : 53
# Z3 status  : unverifiable
# Z3 pattern : conditional_assignment
# Z3 lat ms  : 47.0
#
# SAS: data customer_summary;
# SAS:     set transactions;
# SAS:     by customer_id;
# SAS:     retain running_total 0 tx_count 0;
# SAS:     if first.customer_id then do;
# SAS:         running_total = 0;
# SAS:         tx_count = 0;
# SAS:     end;
# SAS:     running_total + amount;
# SAS:     tx_count + 1;
# SAS:     if last.customer_id then output;
# SAS: run;
# ============================================================================

import pandas as pd

# Ensure data is sorted by customer_id (required for groupby)
df = transactions.sort_values('customer_id')

# Group by customer_id: aggregate to get final totals per customer
# dropna=False mirrors SAS behavior for BY-group processing with missing values
customer_summary = df.groupby('customer_id', dropna=False).agg(
    running_total=('amount', 'sum'),  # equivalent to RETAIN running_total + amount
    tx_count=('amount', 'count')       # equivalent to RETAIN tx_count + 1
).reset_index()

# ============================================================================
# Block 02  2. Missing value logic (SAS . < any number)
# Risk       : LOW
# SAS lines  : 7
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 9.3s
# Tokens     : 1048  (329 prompt + 719 completion)
# tok/s      : 77
# Z3 status  : unverifiable
# Z3 pattern : boolean_filter
# Z3 lat ms  : 0.0
#
# SAS: data cleaned;
# SAS:     set raw_data;
# SAS:     if age = . then age = 0;
# SAS:     if score < . then flag = 'MISSING';
# SAS:     else if score > 100 then flag = 'INVALID';
# SAS:     else flag = 'OK';
# SAS: run;
# ============================================================================

import pandas as pd
import numpy as np

# Copy to avoid modifying raw_data
cleaned = raw_data.copy()

# If age is missing, fill with 0
cleaned['age'] = cleaned['age'].fillna(0)

# Create flag based on score conditions (SAS: . = missing, treated as smallest value)
cleaned['flag'] = np.select(
    condlist=[
        cleaned['score'].isna(),    # score < . in SAS
        cleaned['score'] > 100      # score > 100
    ],
    choicelist=['MISSING', 'INVALID'],
    default='OK'
)

# ============================================================================
# Block 03  3. PROC SQL with correlated subquery
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 10.9s
# Tokens     : 1363  (389 prompt + 974 completion)
# tok/s      : 90
# Z3 status  : unverifiable
# Z3 pattern : boolean_filter
# Z3 lat ms  : 15.0
#
# SAS: proc sql;
# SAS:     create table high_value as
# SAS:     select t.customer_id,
# SAS:            t.amount,
# SAS:            avg_t.avg_amount
# SAS:     from transactions t
# SAS:     inner join (
# SAS:         select customer_id,
# SAS:                mean(amount) as avg_amount
# SAS:         from transactions
# SAS:         group by customer_id
# SAS:     ) avg_t on t.customer_id = avg_t.customer_id
# SAS:     where t.amount > avg_t.avg_amount * 1.5;
# SAS: quit;
# ============================================================================

import pandas as pd

# Compute average amount per customer from transactions
avg_amounts = transactions.groupby('customer_id', as_index=False)['amount'].mean()
avg_amounts.rename(columns={'amount': 'avg_amount'}, inplace=True)

# Inner join with aggregated averages (SAS semantics preserved)
high_value = pd.merge(
    transactions,
    avg_amounts,
    on='customer_id',
    how='inner'
)

# Filter: amount > 1.5 * avg_amount
high_value = high_value[high_value['amount'] > high_value['avg_amount'] * 1.5]
high_value = high_value[['customer_id', 'amount', 'avg_amount']]

# ============================================================================
# Block 04  4. Macro with parameters + %DO loop
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 22.0s
# Tokens     : 1458  (378 prompt + 1080 completion)
# tok/s      : 49
# Z3 status  : unverifiable
# Z3 pattern : conditional_assignment
# Z3 lat ms  : 0.0
#
# SAS: %macro rolling_mean(dsn=, var=, window=3, out=);
# SAS:     data &out;
# SAS:         set &dsn;
# SAS:         array vals{&window} _temporary_;
# SAS:         retain idx 0;
# SAS:         idx = mod(idx, &window) + 1;
# SAS:         vals{idx} = &var;
# SAS:         if _n_ >= &window then
# SAS:             &var._ma = mean(of vals{*});
# SAS:         else
# SAS:             &var._ma = .;
# SAS:     run;
# SAS: %mend;
# SAS: 
# SAS: %rolling_mean(dsn=prices, var=close, window=5, out=prices_ma);
# ============================================================================

import pandas as pd

def rolling_mean(df, var='close', window=5, out=None):
    """
    Compute rolling mean using a circular buffer approach.
    Equivalent to the SAS %rolling_mean macro.
    
    Args:
        df: Input DataFrame
        var: Variable name for which to compute rolling mean
        window: Rolling window size (default: 5)
        out: Optional output DataFrame name (for compatibility)
    Returns:
        DataFrame with new column {var}_ma
    """
    result = df.copy()
    # Compute rolling mean; set NaN where insufficient observations
    result[f'{var}_ma'] = result[var].rolling(window=window, min_periods=window).mean()
    return result


# Example usage:
# prices_ma = rolling_mean(prices, var='close', window=5)

# ============================================================================
# Block 05  5. PROC MEANS with CLASS and OUTPUT
# Risk       : LOW
# SAS lines  : 8
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 13.3s
# Tokens     : 1152  (335 prompt + 817 completion)
# tok/s      : 61
# Z3 status  : formal_proof
# Z3 pattern : proc_means_groupby
# Z3 lat ms  : 0.0
#
# SAS: proc means data=sales noprint;
# SAS:     class region product_line;
# SAS:     var revenue units_sold;
# SAS:     output out=summary(drop=_type_ _freq_)
# SAS:         mean=avg_revenue avg_units
# SAS:         sum=total_revenue total_units
# SAS:         n=obs_count;
# SAS: run;
# ============================================================================

import pandas as pd

# Equivalent to: proc means data=sales; class region product_line; var revenue units_sold;
# SAS _type_ and _freq_ columns are metadata and not produced by pandas groupby
summary = (
    sales
    .groupby(['region', 'product_line'], dropna=False)
    .agg(
        avg_revenue=('revenue', 'mean'),
        total_revenue=('revenue', 'sum'),
        obs_count=('revenue', 'count'),
        avg_units=('units_sold', 'mean'),
        total_units=('units_sold', 'sum')
    )
    .reset_index()
)

# ============================================================================
# Block 06  6. PROC SORT NODUPKEY
# Risk       : LOW
# SAS lines  : 3
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 4.4s
# Tokens     : 495  (280 prompt + 215 completion)
# tok/s      : 49
# Z3 status  : formal_proof
# Z3 pattern : sort_nodupkey
# Z3 lat ms  : 0.0
#
# SAS: proc sort data=customers nodupkey;
# SAS:     by customer_id;
# SAS: run;
# ============================================================================

customers = customers.sort_values('customer_id').drop_duplicates(subset=['customer_id'])

# ============================================================================
# Block 07  7. Hash object for lookup
# Risk       : HIGH
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 15.0s
# Tokens     : 1250  (366 prompt + 884 completion)
# tok/s      : 59
# Z3 status  : unverifiable
# Z3 pattern : conditional_assignment
# Z3 lat ms  : 16.0
#
# SAS: data enriched;
# SAS:     if _n_ = 1 then do;
# SAS:         declare hash h(dataset: 'lookup_table');
# SAS:         h.defineKey('product_id');
# SAS:         h.defineData('product_name', 'category');
# SAS:         h.defineDone();
# SAS:     end;
# SAS:     set transactions;
# SAS:     rc = h.find();
# SAS:     if rc ^= 0 then product_name = 'UNKNOWN';
# SAS: run;
# ============================================================================

import pandas as pd

# Merge transactions with lookup_table on product_id (left join)
# This mimics the SAS hash lookup behavior
enriched = transactions.merge(
    lookup_table[['product_id', 'product_name', 'category']],
    on='product_id',
    how='left'
)

# If product_name is not found (rc ^= 0 in SAS), set to 'UNKNOWN'
enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')

# ============================================================================
# Block 08  8. Multi-level nested macro
# Risk       : MOD
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.85
# Latency    : 9.4s
# Tokens     : 1224  (386 prompt + 838 completion)
# tok/s      : 89
# Z3 status  : unverifiable
# Z3 pattern : proc_means_groupby
# Z3 lat ms  : 0.0
#
# SAS: %macro apply_to_all(action=, datasets=);
# SAS:     %let n = %sysfunc(countw(&datasets));
# SAS:     %do i = 1 %to &n;
# SAS:         %let ds = %scan(&datasets, &i);
# SAS:         %&action(dsn=&ds);
# SAS:     %end;
# SAS: %mend;
# SAS: 
# SAS: %macro summarise(dsn=);
# SAS:     proc means data=&dsn; run;
# SAS: %mend;
# SAS: 
# SAS: %apply_to_all(action=summarise, datasets=sales returns inventory);
# ============================================================================

import pandas as pd

# Macro equivalent: apply_to_all(action=, datasets=)
def apply_to_all(action, datasets_str):
    """Apply action function to each space-separated dataset name."""
    datasets = datasets_str.split()
    for ds in datasets:
        action(dsn=ds)

# Macro equivalent: summarise(dsn=)
def summarise(dsn):
    """Run descriptive statistics on a dataset (equivalent to PROC MEANS)."""
    # Assumes dataframes exist in globals() or dict; adjust loading as needed
    df = globals().get(dsn)
    if df is not None:
        print(f"=== PROC MEANS for {dsn} ===")
        print(df.describe())

# Execute: %apply_to_all(action=summarise, datasets=sales returns inventory)
apply_to_all(summarise, "sales returns inventory")

# ============================================================================
# Block 09  9. PROC TRANSPOSE
# Risk       : LOW
# SAS lines  : 5
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 10.7s
# Tokens     : 966  (300 prompt + 666 completion)
# tok/s      : 62
# Z3 status  : unverifiable
# Z3 pattern : -
# Z3 lat ms  : 0.0
#
# SAS: proc transpose data=monthly_sales out=wide_sales prefix=month_;
# SAS:     by product_id;
# SAS:     id month;
# SAS:     var revenue;
# SAS: run;
# ============================================================================

import pandas as pd

# PROC TRANSPOSE equivalent: pivot from long to wide format
# by product_id  -> index (rows)
# id month       -> columns (with prefix added)
# var revenue    -> values
wide_sales = monthly_sales.pivot(index='product_id', columns='month', values='revenue')

# Add prefix to column names (SAS prefix=month_)
wide_sales.columns = 'month_' + wide_sales.columns.astype(str)

# Reset index so product_id becomes a column (similar to SAS output structure)
wide_sales = wide_sales.reset_index()

# ============================================================================
# Block 10  10. Complex WHERE + FORMAT + LABEL
# Risk       : LOW
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 16.4s
# Tokens     : 1108  (334 prompt + 774 completion)
# tok/s      : 47
# Z3 status  : formal_proof
# Z3 pattern : boolean_filter
# Z3 lat ms  : 0.0
#
# SAS: data report;
# SAS:     set survey;
# SAS:     where age >= 18 and age <= 65
# SAS:           and status in ('ACTIVE', 'PENDING')
# SAS:           and score ^= .;
# SAS:     format score 8.2
# SAS:            survey_date date9.;
# SAS:     label score = 'Survey Score (0-100)'
# SAS:           survey_date = 'Date of Survey';
# SAS:     score_pct = score / 100;
# SAS: run;
# ============================================================================

import pandas as pd
import numpy as np

# Filter: age 18-65, status in ('ACTIVE','PENDING'), score not missing
report = survey[
    (survey['age'] >= 18) &
    (survey['age'] <= 65) &
    (survey['status'].isin(['ACTIVE', 'PENDING'])) &
    (survey['score'].notna())  # score ^= . means not missing
].copy()

# Create derived column
report['score_pct'] = report['score'] / 100

# Optional: preserve SAS-style column labels as DataFrame metadata
report.attrs['column_labels'] = {
    'score': 'Survey Score (0-100)',
    'survey_date': 'Date of Survey'
}
