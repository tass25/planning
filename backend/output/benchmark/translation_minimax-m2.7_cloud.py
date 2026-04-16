"""
translation_minimax-m2.7_cloud.py

Model        : minimax-m2.7:cloud
Generated    : 2026-04-15T21:23:38.260591+00:00
Blocks       : 10
Success      : 10/10  (100%)
Z3 proved    : 3/10
Mean latency : 16.7s
Total tokens : 10,267
"""

# ============================================================================
# Block 01  1. RETAIN + BY-group FIRST./LAST.
# Risk       : HIGH
# SAS lines  : 12
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 10.1s
# Tokens     : 974  (325 prompt + 649 completion)
# tok/s      : 64
# Z3 status  : unverifiable
# Z3 pattern : conditional_assignment
# Z3 lat ms  : 172.0
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

# Group by customer_id and aggregate: sum of amount, count of transactions
# dropna=False mirrors SAS behavior with missing customer_id values
customer_summary = (
    transactions
    .groupby('customer_id', dropna=False)
    .agg(
        running_total=('amount', 'sum'),
        tx_count=('amount', 'count')
    )
    .reset_index()
)

# ============================================================================
# Block 02  2. Missing value logic (SAS . < any number)
# Risk       : LOW
# SAS lines  : 7
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 11.6s
# Tokens     : 1126  (306 prompt + 820 completion)
# tok/s      : 71
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

cleaned = raw_data.copy()
# Replace missing age with 0
cleaned['age'] = cleaned['age'].fillna(0)
# Create flag based on score conditions (SAS: missing < any value)
cleaned['flag'] = np.select(
    [cleaned['score'].isna(), cleaned['score'] > 100],
    ['MISSING', 'INVALID'],
    default='OK'
)

# ============================================================================
# Block 03  3. PROC SQL with correlated subquery
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 10.5s
# Tokens     : 1119  (344 prompt + 775 completion)
# tok/s      : 74
# Z3 status  : unverifiable
# Z3 pattern : boolean_filter
# Z3 lat ms  : 0.0
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

# Calculate average amount per customer
avg_amounts = transactions.groupby('customer_id', as_index=False)['amount'].mean()
avg_amounts.rename(columns={'amount': 'avg_amount'}, inplace=True)

# Inner join transactions with avg_amounts, then filter for high-value transactions
high_value = pd.merge(
    transactions[['customer_id', 'amount']],
    avg_amounts,
    on='customer_id',
    how='inner'
)
high_value = high_value[high_value['amount'] > high_value['avg_amount'] * 1.5]

# ============================================================================
# Block 04  4. Macro with parameters + %DO loop
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 14.0s
# Tokens     : 1443  (380 prompt + 1063 completion)
# tok/s      : 76
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

def rolling_mean(dsn, var, window=3, out=None):
    """
    Calculate rolling mean using circular buffer (SAS macro equivalent).
    
    Parameters:
    - dsn: DataFrame or path to CSV/SAS file
    - var: variable name to calculate rolling mean on
    - window: window size (default 3)
    - out: output file path (optional)
    
    Returns:
    - DataFrame with new column {var}_ma (missing until window is filled)
    """
    # Handle input - read from file if string, otherwise copy
    if isinstance(dsn, str):
        df = pd.read_csv(dsn)  # or pd.read_sas() for SAS files
    else:
        df = dsn.copy()
    
    # Rolling mean: min_periods=window ensures . for first (window-1) rows
    # This matches SAS behavior where _n_ < window -> missing
    df[f'{var}_ma'] = df[var].rolling(window=window, min_periods=window).mean()
    
    # Write to file if output path specified
    if out:
        df.to_csv(out, index=False)  # or df.to_sas(out) for SAS format
    
    return df


# Usage example (equivalent to %rolling_mean macro call)
prices_ma = rolling_mean(dsn='prices', var='close', window=5, out='prices_ma')

# ============================================================================
# Block 05  5. PROC MEANS with CLASS and OUTPUT
# Risk       : LOW
# SAS lines  : 8
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 13.1s
# Tokens     : 877  (313 prompt + 564 completion)
# tok/s      : 43
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

summary = (
    sales
    .groupby(['region', 'product_line'], dropna=False)
    .agg(
        avg_revenue=('revenue', 'mean'),
        avg_units=('units_sold', 'mean'),
        total_revenue=('revenue', 'sum'),
        total_units=('units_sold', 'sum'),
        obs_count=('revenue', 'count')  # n= counts non-missing obs; 'count' is equivalent
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
# Latency    : 6.7s
# Tokens     : 629  (269 prompt + 360 completion)
# tok/s      : 54
# Z3 status  : formal_proof
# Z3 pattern : sort_nodupkey
# Z3 lat ms  : 0.0
#
# SAS: proc sort data=customers nodupkey;
# SAS:     by customer_id;
# SAS: run;
# ============================================================================

import pandas as pd

# Remove duplicate customer_ids, keeping first occurrence
customers = customers.drop_duplicates(subset=['customer_id'], keep='first')

# ============================================================================
# Block 07  7. Hash object for lookup
# Risk       : HIGH
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 10.0s
# Tokens     : 958  (329 prompt + 629 completion)
# tok/s      : 63
# Z3 status  : unverifiable
# Z3 pattern : conditional_assignment
# Z3 lat ms  : 0.0
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

# Load both datasets
transactions = pd.read_csv('transactions.csv')
lookup_table = pd.read_csv('lookup_table.csv')

# Perform left join on product_id (equivalent to hash lookup)
enriched = transactions.merge(
    lookup_table[['product_id', 'product_name', 'category']],
    on='product_id',
    how='left'
)

# Fill missing product_name values with 'UNKNOWN' (equivalent to rc ^= 0 check)
enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')

# ============================================================================
# Block 08  8. Multi-level nested macro
# Risk       : MOD
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.85
# Latency    : 25.5s
# Tokens     : 1264  (355 prompt + 909 completion)
# tok/s      : 36
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

def apply_to_all(action, datasets):
    """Iterate over space-separated dataset names and apply action to each.
    Equivalent to SAS %apply_to_all macro."""
    for ds in datasets.split():  # split on whitespace like SAS COUNTW
        action(dsn=ds)

def summarise(dsn):
    """Print descriptive statistics for a dataset (equivalent to PROC MEANS).
    Assumes datasets are available as pandas DataFrames in a dict or loaded from CSV."""
    # In practice, load from your data source; here we assume a dict of DataFrames
    if isinstance(dsn, pd.DataFrame):
        df = dsn
    else:
        df = pd.read_csv(f"{dsn}.csv")  # adjust path as needed
    print(df.describe())

# Call the macro equivalent: apply summarise to sales, returns, inventory
apply_to_all(action=summarise, datasets='sales returns inventory')

# ============================================================================
# Block 09  9. PROC TRANSPOSE
# Risk       : LOW
# SAS lines  : 5
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 31.2s
# Tokens     : 873  (285 prompt + 588 completion)
# tok/s      : 19
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
wide_sales = monthly_sales.pivot(index='product_id', columns='month', values='revenue')
# Add SAS-style prefix to column names
wide_sales.columns = [f'month_{col}' for col in wide_sales.columns]
wide_sales = wide_sales.reset_index()

# ============================================================================
# Block 10  10. Complex WHERE + FORMAT + LABEL
# Risk       : LOW
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 34.0s
# Tokens     : 1004  (336 prompt + 668 completion)
# tok/s      : 20
# Z3 status  : formal_proof
# Z3 pattern : boolean_filter
# Z3 lat ms  : 15.0
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

# Assuming 'survey' DataFrame is already loaded
report = survey.copy()

# Filter: age 18-65, status ACTIVE/PENDING, score not missing
report = report[
    (report['age'] >= 18) &
    (report['age'] <= 65) &
    (report['status'].isin(['ACTIVE', 'PENDING'])) &
    (report['score'].notna())
]

# Create calculated column
report['score_pct'] = report['score'] / 100

# Note: SAS FORMAT/LABEL statements are metadata-only;
# pandas stores data, formatting applied at display/export time
