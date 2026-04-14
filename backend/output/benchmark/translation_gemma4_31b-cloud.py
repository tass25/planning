"""
translation_gemma4_31b-cloud.py

Model        : gemma4:31b-cloud
Generated    : 2026-04-12T22:17:21.324524+00:00
Blocks       : 10
Success      : 10/10  (100%)
Z3 proved    : 3/10
Mean latency : 7.8s
Total tokens : 6,188
"""

# ============================================================================
# Block 01  1. RETAIN + BY-group FIRST./LAST.
# Risk       : HIGH
# SAS lines  : 12
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 6.8s
# Tokens     : 563  (363 prompt + 200 completion)
# tok/s      : 30
# Z3 status  : unverifiable
# Z3 pattern : conditional_assignment
# Z3 lat ms  : 46.0
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
import numpy as np

# SAS 'by customer_id' and 'retain' logic for totals is equivalent to a groupby aggregation
# The 'if last.customer_id then output' means we only keep the final aggregated row per customer
customer_summary = transactions.groupby('customer_id', as_index=False).agg(
    running_total=('amount', 'sum'),
    tx_count=('amount', 'size')
)

# ============================================================================
# Block 02  2. Missing value logic (SAS . < any number)
# Risk       : LOW
# SAS lines  : 7
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 8.5s
# Tokens     : 638  (330 prompt + 308 completion)
# tok/s      : 36
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

# Create a copy to simulate the DATA step
cleaned = raw_data.copy()

# if age = . then age = 0;
cleaned['age'] = cleaned['age'].fillna(0)

# Logic for flag based on score
# SAS 'score < .' checks if score is not missing
conditions = [
    (cleaned['score'].notna()),
    (cleaned['score'] > 100)
]
choices = ['MISSING', 'INVALID']

# Note: The original SAS logic has a potential overlap/contradiction 
# (if score is not missing, it immediately sets 'MISSING'). 
# To preserve exact SAS semantics: 
cleaned['flag'] = np.select(
    [
        cleaned['score'].notna(),
        cleaned['score'] > 100
    ],
    ['MISSING', 'INVALID'],
    default='OK'
)

# ============================================================================
# Block 03  3. PROC SQL with correlated subquery
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 7.1s
# Tokens     : 621  (384 prompt + 237 completion)
# tok/s      : 33
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
import numpy as np

# Calculate average amount per customer (equivalent to the inner join subquery)
avg_t = transactions.groupby('customer_id', as_index=False)['amount'].mean().rename(columns={'amount': 'avg_amount'})

# Perform inner join
merged = pd.merge(transactions, avg_t, on='customer_id', how='inner')

# Filter rows where amount is greater than 1.5 times the average
high_value = merged[merged['amount'] > merged['avg_amount'] * 1.5][['customer_id', 'amount', 'avg_amount']]

# ============================================================================
# Block 04  4. Macro with parameters + %DO loop
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 9.3s
# Tokens     : 748  (410 prompt + 338 completion)
# tok/s      : 36
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
import numpy as np

def rolling_mean(df, var, window=3):
    """
    Translates the SAS macro logic: 
    Calculates a rolling mean for a specific column.
    SAS logic uses a temporary array to simulate a sliding window.
    """
    df_out = df.copy()
    # pandas.rolling() is the idiomatic equivalent to the SAS array/retain logic
    # window=window ensures the mean is only calculated when the window is full
    df_out[f"{var}_ma"] = df_out[var].rolling(window=window).mean()
    
    # SAS logic: if _n_ < window then . (NaN in pandas)
    # pandas.rolling().mean() naturally produces NaN for the first (window-1) rows
    return df_out

# Execution equivalent to %rolling_mean(dsn=prices, var=close, window=5, out=prices_ma);
prices_ma = rolling_mean(prices, var='close', window=5)

# ============================================================================
# Block 05  5. PROC MEANS with CLASS and OUTPUT
# Risk       : LOW
# SAS lines  : 8
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 9.4s
# Tokens     : 681  (337 prompt + 344 completion)
# tok/s      : 37
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
import numpy as np

# PROC MEANS with CLASS and OUTPUT
# Group by class variables and aggregate specified variables
summary = sales.groupby(['region', 'product_line'], dropna=False).agg({
    'revenue': ['mean', 'sum', 'count'],
    'units_sold': ['mean', 'sum', 'count']
})

# Flatten multi-index columns to match SAS output names
summary.columns = [
    'avg_revenue', 'total_revenue', 'obs_count_rev', 
    'avg_units', 'total_units', 'obs_count_units'
]

# SAS 'n=' for multiple variables produces the same count if no missing values differ,
# but to strictly match the 'obs_count' request for the group:
summary['obs_count'] = summary['obs_count_rev']
summary = summary.drop(columns=['obs_count_rev', 'obs_count_units'])

# Reset index to move class variables back into columns (matching SAS output dataset)
summary = summary.reset_index()

# ============================================================================
# Block 06  6. PROC SORT NODUPKEY
# Risk       : LOW
# SAS lines  : 3
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 4.4s
# Tokens     : 386  (287 prompt + 99 completion)
# tok/s      : 22
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
# Confidence : 1.00
# Latency    : 9.7s
# Tokens     : 603  (363 prompt + 240 completion)
# tok/s      : 25
# Z3 status  : unverifiable
# Z3 pattern : conditional_assignment
# Z3 lat ms  : 15.0
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
import numpy as np

# The SAS hash object is functionally equivalent to a left join in pandas
# We merge 'transactions' with 'lookup_table' on 'product_id'
enriched = pd.merge(
    transactions, 
    lookup_table[['product_id', 'product_name', 'category']], 
    on='product_id', 
    how='left'
)

# SAS: if rc ^= 0 then product_name = 'UNKNOWN';
# This handles cases where the lookup failed (NaN after left join)
enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')

# ============================================================================
# Block 08  8. Multi-level nested macro
# Risk       : MOD
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 9.4s
# Tokens     : 761  (387 prompt + 374 completion)
# tok/s      : 40
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
import numpy as np

# Mocking the datasets for demonstration purposes
# In a real scenario, these would be existing DataFrames in the environment
datasets_dict = {
    'sales': pd.DataFrame({'amount': [10, 20, 30]}),
    'returns': pd.DataFrame({'amount': [1, 2, 3]}),
    'inventory': pd.DataFrame({'amount': [100, 200, 300]})
}

def summarise(df_name):
    """Equivalent to PROC MEANS: calculates basic descriptive statistics"""
    df = datasets_dict.get(df_name)
    if df is not None:
        print(f"--- Summary for {df_name} ---")
        print(df.describe())
        print('\n')

def apply_to_all(action_func, datasets):
    """Equivalent to the %apply_to_all macro loop"""
    for ds in datasets:
        action_func(ds)

# Execution
list_of_datasets = ['sales', 'returns', 'inventory']
apply_to_all(summarise, list_of_datasets)

# ============================================================================
# Block 09  9. PROC TRANSPOSE
# Risk       : LOW
# SAS lines  : 5
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 5.7s
# Tokens     : 505  (304 prompt + 201 completion)
# tok/s      : 35
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

# PROC TRANSPOSE with BY and ID statements is equivalent to a pivot operation
wide_sales = monthly_sales.pivot(index='product_id', columns='month', values='revenue')

# SAS 'prefix=month_' adds a prefix to the new column names
wide_sales.columns = [f'month_{col}' for col in wide_sales.columns]

# Reset index to bring product_id back as a column, matching SAS output behavior
wide_sales = wide_sales.reset_index()

# ============================================================================
# Block 10  10. Complex WHERE + FORMAT + LABEL
# Risk       : LOW
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 7.7s
# Tokens     : 682  (366 prompt + 316 completion)
# tok/s      : 41
# Z3 status  : formal_proof
# Z3 pattern : boolean_filter
# Z3 lat ms  : 16.0
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

# Filter data based on WHERE clause
# SAS 'score ^= .' means score is not missing
report = survey[(
    (survey['age'] >= 18) &
    (survey['age'] <= 65) &
    (survey['status'].isin(['ACTIVE', 'PENDING'])) &
    (survey['score'].notna())
)].copy()

# Calculate new column
report['score_pct'] = report['score'] / 100

# SAS Formats and Labels are metadata; in pandas we handle this via renaming or custom display
# To mimic labels, we can store them in a dictionary or rename columns
report.rename(columns={
    'score': 'Survey Score (0-100)',
    'survey_date': 'Date of Survey'
}, inplace=False) # Note: renaming changes the column keys; usually labels are kept as a separate map
