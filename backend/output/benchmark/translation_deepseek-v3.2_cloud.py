"""
translation_deepseek-v3.2_cloud.py

Model        : deepseek-v3.2:cloud
Generated    : 2026-04-12T22:23:16.956301+00:00
Blocks       : 10
Success      : 4/10  (40%)
Z3 proved    : 2/10
Mean latency : 61.7s
Total tokens : 19,857
"""

# ============================================================================
# Block 01  1. RETAIN + BY-group FIRST./LAST.
# Risk       : HIGH
# SAS lines  : 12
# Status     : PARTIAL
# Syntax OK  : False
# Confidence : 0.50
# Latency    : 77.8s
# Tokens     : 2373  (325 prompt + 2048 completion)
# tok/s      : 26
# Z3 status  : skipped
# Z3 pattern : -
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

# PARTIAL: empty python_code after parse

# ============================================================================
# Block 02  2. Missing value logic (SAS . < any number)
# Risk       : LOW
# SAS lines  : 7
# Status     : PARTIAL
# Syntax OK  : False
# Confidence : 0.50
# Latency    : 76.3s
# Tokens     : 2353  (305 prompt + 2048 completion)
# tok/s      : 27
# Z3 status  : skipped
# Z3 pattern : -
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

# PARTIAL: empty python_code after parse

# ============================================================================
# Block 03  3. PROC SQL with correlated subquery
# Risk       : MOD
# SAS lines  : 14
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 33.1s
# Tokens     : 1169  (347 prompt + 822 completion)
# tok/s      : 25
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

# Compute average amount per customer
avg_amounts = transactions.groupby('customer_id')['amount'].mean().reset_index()
avg_amounts.columns = ['customer_id', 'avg_amount']

# Inner join with original transactions and filter
high_value = pd.merge(transactions, avg_amounts, on='customer_id', how='inner')
high_value = high_value[high_value['amount'] > high_value['avg_amount'] * 1.5]

# Select required columns
high_value = high_value[['customer_id', 'amount', 'avg_amount']]

# ============================================================================
# Block 04  4. Macro with parameters + %DO loop
# Risk       : MOD
# SAS lines  : 14
# Status     : PARTIAL
# Syntax OK  : False  error: line 2: unterminated string literal (detected at line 2)
# Confidence : 0.50
# Latency    : 75.9s
# Tokens     : 2428  (380 prompt + 2048 completion)
# tok/s      : 27
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

{
  "python_code": "import pandas as pd\nimport numpy as np\n\n# Replicate SAS rolling mean macro with circular buffer\n# Note: This implementation uses pandas rolling window for efficiency\n# but maintains the same

# ============================================================================
# Block 05  5. PROC MEANS with CLASS and OUTPUT
# Risk       : LOW
# SAS lines  : 8
# Status     : PARTIAL
# Syntax OK  : False
# Confidence : 0.50
# Latency    : 76.4s
# Tokens     : 2363  (315 prompt + 2048 completion)
# tok/s      : 27
# Z3 status  : skipped
# Z3 pattern : -
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

# PARTIAL: empty python_code after parse

# ============================================================================
# Block 06  6. PROC SORT NODUPKEY
# Risk       : LOW
# SAS lines  : 3
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 34.5s
# Tokens     : 1164  (267 prompt + 897 completion)
# tok/s      : 26
# Z3 status  : formal_proof
# Z3 pattern : sort_nodupkey
# Z3 lat ms  : 0.0
#
# SAS: proc sort data=customers nodupkey;
# SAS:     by customer_id;
# SAS: run;
# ============================================================================

import pandas as pd

# PROC SORT NODUPKEY: sort and remove duplicates by key
customers = customers.sort_values(by='customer_id').drop_duplicates(subset='customer_id')

# ============================================================================
# Block 07  7. Hash object for lookup
# Risk       : HIGH
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 36.5s
# Tokens     : 1301  (333 prompt + 968 completion)
# tok/s      : 27
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

# Load datasets (assuming they exist as DataFrames)
# lookup_table = pd.read_csv('lookup_table.csv')  # Example if reading from file
# transactions = pd.read_csv('transactions.csv')

# Perform hash join equivalent: left join on product_id
enriched = pd.merge(
    transactions,
    lookup_table[['product_id', 'product_name', 'category']],
    on='product_id',
    how='left'
)

# Set product_name to 'UNKNOWN' where join failed (missing in lookup)
enriched['product_name'] = np.where(
    enriched['product_name'].isna(),
    'UNKNOWN',
    enriched['product_name']
)

# Note: category remains NaN where join failed (as in SAS hash object behavior)

# ============================================================================
# Block 08  8. Multi-level nested macro
# Risk       : MOD
# SAS lines  : 11
# Status     : PARTIAL
# Syntax OK  : False  error: line 2: unterminated string literal (detected at line 2)
# Confidence : 0.50
# Latency    : 72.8s
# Tokens     : 2404  (356 prompt + 2048 completion)
# tok/s      : 28
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

{
  "python_code": "import pandas as pd\nimport numpy as np\n\n# Define function to apply to multiple datasets\ndef apply_to_all(action, datasets):\n    \"\"\"Apply given function to list of dataset names\"\"\"\n    for ds in datasets:\n        action(dsn=ds)\n\n# Define summary function\ndef summarise(dsn):\n    \"\"\"Print summary statistics for given DataFrame name\"\"\"\n

# ============================================================================
# Block 09  9. PROC TRANSPOSE
# Risk       : LOW
# SAS lines  : 5
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 59.6s
# Tokens     : 1917  (282 prompt + 1635 completion)
# tok/s      : 27
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

# Transpose long to wide format (PROC TRANSPOSE equivalent)
wide_sales = monthly_sales.pivot(
    index='product_id',  # BY variable
    columns='month',     # ID variable for column names
    values='revenue'     # VAR variable to transpose
).add_prefix('month_').reset_index()  # Add prefix and reset index to match SAS output structure

# ============================================================================
# Block 10  10. Complex WHERE + FORMAT + LABEL
# Risk       : LOW
# SAS lines  : 11
# Status     : PARTIAL
# Syntax OK  : False
# Confidence : 0.50
# Latency    : 74.3s
# Tokens     : 2385  (337 prompt + 2048 completion)
# tok/s      : 28
# Z3 status  : skipped
# Z3 pattern : -
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

# PARTIAL: empty python_code after parse
