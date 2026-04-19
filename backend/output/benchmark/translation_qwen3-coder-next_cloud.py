"""
translation_qwen3-coder-next_cloud.py

Model        : qwen3-coder-next:cloud
Generated    : 2026-04-12T22:12:59.659584+00:00
Blocks       : 10
Success      : 10/10  (100%)
Z3 proved    : 3/10
Mean latency : 4.7s
Total tokens : 5,414
"""

# ============================================================================
# Block 01  1. RETAIN + BY-group FIRST./LAST.
# Risk       : HIGH
# SAS lines  : 12
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 4.9s
# Tokens     : 582  (316 prompt + 266 completion)
# tok/s      : 54
# Z3 status  : unverifiable
# Z3 pattern : conditional_assignment
# Z3 lat ms  : 0.0
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

# Group by customer_id and compute cumulative sum of amount and count of transactions
# Only keep the last row per customer (equivalent to output on last.customer_id)
customer_summary = transactions.groupby('customer_id', dropna=False).agg(
    running_total=('amount', 'cumsum'),  # cumulative sum
    tx_count=('amount', 'cumcount')      # 0-indexed cumcount; add 1 to match SAS 1-indexed count
).reset_index()

# Adjust tx_count to be 1-indexed (SAS counts start at 1)
customer_summary['tx_count'] = customer_summary['tx_count'] + 1

# Keep only the last row per group (equivalent to output on last.customer_id)
customer_summary = customer_summary.groupby('customer_id', dropna=False).tail(1)

# ============================================================================
# Block 02  2. Missing value logic (SAS . < any number)
# Risk       : LOW
# SAS lines  : 7
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 3.8s
# Tokens     : 452  (299 prompt + 153 completion)
# tok/s      : 40
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
cleaned['age'] = cleaned['age'].fillna(0)  # Replace missing age with 0
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
# Confidence : 1.00
# Latency    : 4.1s
# Tokens     : 507  (333 prompt + 174 completion)
# tok/s      : 43
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

# Compute average amount per customer
avg_df = transactions.groupby('customer_id', dropna=False)['amount'].mean().reset_index(name='avg_amount')

# Merge with original transactions and filter
high_value = pd.merge(transactions, avg_df, on='customer_id', how='inner')
high_value = high_value[high_value['amount'] > high_value['avg_amount'] * 1.5].reset_index(drop=True)

# ============================================================================
# Block 04  4. Macro with parameters + %DO loop
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 6.3s
# Tokens     : 768  (369 prompt + 399 completion)
# tok/s      : 64
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

# Assuming 'prices' is a pandas DataFrame with at least a 'close' column
# The SAS macro computes a rolling mean over a fixed-size window using a circular buffer
# Here we replicate it using pandas' rolling (but note: SAS uses a fixed-size sliding window, not expanding)

# Load data (assuming 'prices' DataFrame already exists)
# prices = pd.read_csv('prices.csv')  # Uncomment if loading from file

# Ensure 'close' column exists
if 'close' not in prices.columns:
    raise ValueError("DataFrame 'prices' must contain a 'close' column")

# Initialize output DataFrame (copy input to preserve original)
prices_ma = prices.copy()

# Compute rolling mean with fixed window size (5), matching SAS behavior:
# - SAS uses a circular buffer of size 5 (not a trailing window)
# - However, for a simple moving average, SAS's circular buffer and trailing window are equivalent
#   *if* data is processed in order and no missing values intervene
# - pandas rolling(window=5, min_periods=5) ensures only full windows are computed
prices_ma['close_ma'] = prices_ma['close'].rolling(window=5, min_periods=5).mean()

# Set first 4 values to NaN (matching SAS: . for _n_ < window)
prices_ma.loc[:4, 'close_ma'] = np.nan

# ============================================================================
# Block 05  5. PROC MEANS with CLASS and OUTPUT
# Risk       : LOW
# SAS lines  : 8
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 4.5s
# Tokens     : 486  (302 prompt + 184 completion)
# tok/s      : 41
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

# Assuming 'sales' is a pandas DataFrame
summary = sales.groupby(['region', 'product_line'], dropna=False).agg(
    avg_revenue=('revenue', 'mean'),
    avg_units=('units_sold', 'mean'),
    total_revenue=('revenue', 'sum'),
    total_units=('units_sold', 'sum'),
    obs_count=('revenue', 'count')  # count non-null values in revenue column
).reset_index()

# ============================================================================
# Block 06  6. PROC SORT NODUPKEY
# Risk       : LOW
# SAS lines  : 3
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 3.2s
# Tokens     : 333  (260 prompt + 73 completion)
# tok/s      : 23
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
# Latency    : 4.7s
# Tokens     : 506  (320 prompt + 186 completion)
# tok/s      : 40
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
import numpy as np

# Load lookup table and transactions
lookup_table = pd.read_csv('lookup_table.csv')  # or however it's loaded
transactions = pd.read_csv('transactions.csv')  # or however it's loaded

# Merge lookup table on product_id (left join)
enriched = transactions.merge(lookup_table[['product_id', 'product_name', 'category']], on='product_id', how='left')

# Replace missing product_name with 'UNKNOWN'
enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')

# ============================================================================
# Block 08  8. Multi-level nested macro
# Risk       : MOD
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.85
# Latency    : 5.5s
# Tokens     : 622  (344 prompt + 278 completion)
# tok/s      : 50
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

# Simulate applying a function to multiple datasets
# Since actual SAS datasets aren't available, we assume they're loaded as DataFrames
# e.g., sales, returns, inventory = pd.read_sas(...), etc.

def summarise(df):
    # Equivalent to PROC MEANS: compute descriptive statistics
    return df.describe()

def apply_to_all(action, datasets):
    # action: function to apply to each dataset
    # datasets: list of DataFrames (or names if loading externally)
    results = {}
    for ds in datasets:
        # Assume ds is a DataFrame; if it's a name, load it first (not shown here)
        results[ds.name if hasattr(ds, 'name') else str(ds)] = action(ds)
    return results

# Example usage (requires actual DataFrames: sales, returns, inventory)
# datasets = [sales, returns, inventory]
# summaries = apply_to_all(action=summarise, datasets=datasets)

# ============================================================================
# Block 09  9. PROC TRANSPOSE
# Risk       : LOW
# SAS lines  : 5
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 4.7s
# Tokens     : 505  (273 prompt + 232 completion)
# tok/s      : 49
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
import numpy as np

# Assuming 'monthly_sales' is a DataFrame with columns: product_id, month, revenue
# Reshape from long to wide format using pivot_table (similar to PROC TRANSPOSE)
wide_sales = monthly_sales.pivot_table(
    index='product_id',
    columns='month',
    values='revenue',
    aggfunc='first'  # assuming unique revenue per product_id-month; use 'mean' or custom if duplicates exist
).reset_index()

# Rename columns to match SAS prefix=month_ (e.g., 'month_1', 'month_2', ...)
wide_sales.columns = ['product_id'] + [f'month_{col}' for col in wide_sales.columns[1:]]

# ============================================================================
# Block 10  10. Complex WHERE + FORMAT + LABEL
# Risk       : LOW
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 5.6s
# Tokens     : 653  (332 prompt + 321 completion)
# tok/s      : 58
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

# Filter rows and compute derived columns
report = survey[
    (survey['age'] >= 18) &
    (survey['age'] <= 65) &
    (survey['status'].isin(['ACTIVE', 'PENDING'])) &
    (survey['score'].notna())
].copy()

# Format score as float with 2 decimal places (no change to data, just display)
report['score'] = report['score'].round(2)

# Add derived column
report['score_pct'] = report['score'] / 100

# Set column labels (pandas supports metadata via .attrs or .rename_axis, but for display use .rename)
report = report.rename(columns={'score': 'Survey Score (0-100)', 'survey_date': 'Date of Survey'})

# Optionally format survey_date as date (if not already datetime)
# Assuming survey_date is datetime-like; if not, convert first:
# report['survey_date'] = pd.to_datetime(report['survey_date'], errors='coerce')
