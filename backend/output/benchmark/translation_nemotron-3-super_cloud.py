"""
translation_nemotron-3-super_cloud.py

Model        : nemotron-3-super:cloud
Generated    : 2026-04-12T22:21:58.176710+00:00
Blocks       : 10
Success      : 10/10  (100%)
Z3 proved    : 4/10
Mean latency : 5.8s
Total tokens : 5,263
"""

# ============================================================================
# Block 01  1. RETAIN + BY-group FIRST./LAST.
# Risk       : HIGH
# SAS lines  : 12
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 6.7s
# Tokens     : 483  (336 prompt + 147 completion)
# tok/s      : 22
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
import numpy as np
# Assuming 'transactions' DataFrame exists with columns: customer_id, amount
customer_summary = transactions.sort_values('customer_id').groupby('customer_id', as_index=False).agg(
    running_total=('amount', 'sum'),
    tx_count=('amount', 'size')
)

# ============================================================================
# Block 02  2. Missing value logic (SAS . < any number)
# Risk       : LOW
# SAS lines  : 7
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 7.5s
# Tokens     : 495  (321 prompt + 174 completion)
# tok/s      : 23
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

# Assuming raw_data is a pandas DataFrame
cleaned = raw_data.copy()
cleaned['age'] = cleaned['age'].fillna(0)
conditions = [
    cleaned['score'].isna(),
    cleaned['score'] > 100
]
choices = ['MISSING', 'INVALID']
cleaned['flag'] = np.select(conditions, choices, default='OK')

# ============================================================================
# Block 03  3. PROC SQL with correlated subquery
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 4.6s
# Tokens     : 575  (355 prompt + 220 completion)
# tok/s      : 48
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

# Assuming 'transactions' DataFrame exists with columns: customer_id, amount
# Compute average amount per customer
avg_t = transactions.groupby('customer_id', as_index=False)['amount'].mean().rename(columns={'amount': 'avg_amount'})
# Merge with original transactions
high_value = pd.merge(transactions, avg_t, on='customer_id', how='inner')
# Filter rows where amount > 1.5 * avg_amount
high_value = high_value[high_value['amount'] > high_value['avg_amount'] * 1.5][['customer_id', 'amount', 'avg_amount']]

# ============================================================================
# Block 04  4. Macro with parameters + %DO loop
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 11.0s
# Tokens     : 608  (396 prompt + 212 completion)
# tok/s      : 19
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

# Assuming 'prices' is a pandas DataFrame with a 'close' column
# Compute rolling mean with window=5, min_periods=5 to match SAS behavior (first 4 values are NaN)
prices_ma = prices.copy()
prices_ma['close_ma'] = prices_ma['close'].rolling(window=5, min_periods=5).mean()

# ============================================================================
# Block 05  5. PROC MEANS with CLASS and OUTPUT
# Risk       : LOW
# SAS lines  : 8
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 3.7s
# Tokens     : 511  (326 prompt + 185 completion)
# tok/s      : 50
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
# Assuming 'sales' DataFrame is already defined
summary = sales.groupby(['region', 'product_line'], dropna=False).agg(
    avg_revenue=('revenue', 'mean'),
    avg_units=('units_sold', 'mean'),
    total_revenue=('revenue', 'sum'),
    total_units=('units_sold', 'sum'),
    obs_count=('revenue', 'count')
).reset_index()

# ============================================================================
# Block 06  6. PROC SORT NODUPKEY
# Risk       : LOW
# SAS lines  : 3
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 3.4s
# Tokens     : 390  (281 prompt + 109 completion)
# tok/s      : 32
# Z3 status  : formal_proof
# Z3 pattern : sort_nodupkey
# Z3 lat ms  : 0.0
#
# SAS: proc sort data=customers nodupkey;
# SAS:     by customer_id;
# SAS: run;
# ============================================================================

import pandas as pd

# Remove duplicate rows based on 'customer_id', keeping the first occurrence
customers = customers.sort_values('customer_id').drop_duplicates(subset='customer_id')

# ============================================================================
# Block 07  7. Hash object for lookup
# Risk       : HIGH
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 6.3s
# Tokens     : 607  (342 prompt + 265 completion)
# tok/s      : 42
# Z3 status  : formal_proof
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
import numpy as np

# Load lookup table and transactions
h = pd.read_csv('lookup_table')
transactions = pd.read_csv('transactions')

# Create mapping from product_id to product_name and category
product_map = h.set_index('product_id')[['product_name', 'category']].to_dict('index')

# Map product_name and category; fill missing with 'UNKNOWN'
def map_product(row):
    pid = row['product_id']
    if pid in product_map:
        return product_map[pid]['product_name'], product_map[pid]['category']
    else:
        return 'UNKNOWN', 'UNKNOWN'

transactions[['product_name', 'category']] = transactions.apply(map_product, axis=1, result_type='expand')

# Save enriched data
transactions.to_csv('enriched.csv', index=False)

# ============================================================================
# Block 08  8. Multi-level nested macro
# Risk       : MOD
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.90
# Latency    : 4.3s
# Tokens     : 538  (370 prompt + 168 completion)
# tok/s      : 39
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

# Assuming sales, returns, inventory are predefined DataFrames
datasets = {'sales': sales, 'returns': returns, 'inventory': inventory}

for ds_name, df in datasets.items():
    print(f"Summary for {ds_name}:")
    print(df.describe())
    print()

# ============================================================================
# Block 09  9. PROC TRANSPOSE
# Risk       : LOW
# SAS lines  : 5
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 5.0s
# Tokens     : 459  (296 prompt + 163 completion)
# tok/s      : 33
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
# Transpose data from long to wide format: each month becomes a column
wide_sales = monthly_sales.pivot(index='product_id', columns='month', values='revenue')
# Rename columns to add prefix 'month_'
wide_sales.columns = [f'month_{col}' for col in wide_sales.columns]
# Reset index to make product_id a column
wide_sales = wide_sales.reset_index()

# ============================================================================
# Block 10  10. Complex WHERE + FORMAT + LABEL
# Risk       : LOW
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 5.8s
# Tokens     : 597  (356 prompt + 241 completion)
# tok/s      : 42
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

# Assuming 'survey' is a pandas DataFrame
report = survey[
    (survey['age'] >= 18) & 
    (survey['age'] <= 65) & 
    survey['status'].isin(['ACTIVE', 'PENDING']) & 
    survey['score'].notna()
].copy()

report['score'] = report['score'].round(2)
report['score_pct'] = report['score'] / 100

# Note: SAS formats (8.2, date9.) and labels are metadata; 
# pandas does not require explicit format statements for computation.
# Labels can be stored in DataFrame.attrs if needed for documentation.
