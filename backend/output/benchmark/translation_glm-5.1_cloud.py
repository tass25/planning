"""
translation_glm-5.1_cloud.py

Model        : glm-5.1:cloud
Generated    : 2026-04-12T22:25:45.570845+00:00
Blocks       : 10
Success      : 6/10  (60%)
Z3 proved    : 1/10
Mean latency : 14.9s
Total tokens : 17,173
"""

# ============================================================================
# Block 01  1. RETAIN + BY-group FIRST./LAST.
# Risk       : HIGH
# SAS lines  : 12
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 1.00
# Latency    : 12.8s
# Tokens     : 1442  (308 prompt + 1134 completion)
# tok/s      : 89
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

# SAS 'by' + 'retain' + 'if last.x then output' is an idiom for groupby aggregation.
# 'running_total + amount' accumulates the sum, 'tx_count + 1' accumulates the row count.
customer_summary = (
    transactions.groupby('customer_id', dropna=False)
    .agg(
        running_total=('amount', 'sum'),
        tx_count=('amount', 'size')  # 'size' counts all rows per group, matching the SAS +1 logic
    )
    .reset_index()
)

# ============================================================================
# Block 02  2. Missing value logic (SAS . < any number)
# Risk       : LOW
# SAS lines  : 7
# Status     : PARTIAL
# Syntax OK  : False
# Confidence : 0.50
# Latency    : 20.9s
# Tokens     : 2337  (289 prompt + 2048 completion)
# tok/s      : 98
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
# Latency    : 12.0s
# Tokens     : 1395  (325 prompt + 1070 completion)
# tok/s      : 89
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

# Calculate average amount per customer (subquery equivalent)
avg_t = transactions.groupby('customer_id', as_index=False).agg(avg_amount=('amount', 'mean'))

# Inner join transactions with average amounts
merged = pd.merge(transactions, avg_t, on='customer_id', how='inner')

# Filter where amount > 1.5 * avg_amount and select columns
high_value = merged.loc[merged['amount'] > merged['avg_amount'] * 1.5, ['customer_id', 'amount', 'avg_amount']]

# ============================================================================
# Block 04  4. Macro with parameters + %DO loop
# Risk       : MOD
# SAS lines  : 14
# Status     : PARTIAL
# Syntax OK  : False
# Confidence : 0.50
# Latency    : 19.0s
# Tokens     : 2409  (361 prompt + 2048 completion)
# tok/s      : 108
# Z3 status  : skipped
# Z3 pattern : -
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

# PARTIAL: empty python_code after parse

# ============================================================================
# Block 05  5. PROC MEANS with CLASS and OUTPUT
# Risk       : LOW
# SAS lines  : 8
# Status     : PARTIAL
# Syntax OK  : False
# Confidence : 0.50
# Latency    : 13.9s
# Tokens     : 2342  (294 prompt + 2048 completion)
# tok/s      : 148
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
# Latency    : 4.3s
# Tokens     : 464  (252 prompt + 212 completion)
# tok/s      : 49
# Z3 status  : formal_proof
# Z3 pattern : sort_nodupkey
# Z3 lat ms  : 0.0
#
# SAS: proc sort data=customers nodupkey;
# SAS:     by customer_id;
# SAS: run;
# ============================================================================

import pandas as pd

# PROC SORT NODUPKEY: sort by variable(s) and drop duplicate keys
customers = customers.sort_values(by=['customer_id']).drop_duplicates(subset=['customer_id'])

# ============================================================================
# Block 07  7. Hash object for lookup
# Risk       : HIGH
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 4.6s
# Tokens     : 595  (312 prompt + 283 completion)
# tok/s      : 61
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

# SAS hash object lookup -> pandas left merge
enriched = pd.merge(
    transactions,
    lookup_table[['product_id', 'product_name', 'category']],
    on='product_id',
    how='left'
)

# If rc ^= 0 (key not found in hash), set product_name to 'UNKNOWN'
enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')

# ============================================================================
# Block 08  8. Multi-level nested macro
# Risk       : MOD
# SAS lines  : 11
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.90
# Latency    : 12.7s
# Tokens     : 1871  (336 prompt + 1535 completion)
# tok/s      : 121
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

def summarise(df):
    # Equivalent to PROC MEANS without CLASS or VAR statements
    print(df.describe())

def apply_to_all(action, datasets):
    # SAS macro loop over space-separated names translates to a Python for-loop over a list
    for ds in datasets:
        action(ds)

# Example usage (assuming sales, returns, inventory are DataFrames):
# apply_to_all(action=summarise, datasets=[sales, returns, inventory])

# ============================================================================
# Block 09  9. PROC TRANSPOSE
# Risk       : LOW
# SAS lines  : 5
# Status     : SUCCESS
# Syntax OK  : True
# Confidence : 0.95
# Latency    : 20.2s
# Tokens     : 1952  (265 prompt + 1687 completion)
# tok/s      : 84
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

# PROC TRANSPOSE: pivot from long to wide, applying PREFIX to new columns
wide_sales = (
    monthly_sales
    .pivot_table(index='product_id', columns='month', values='revenue', aggfunc='first')
    .rename(columns=lambda c: f'month_{c}')
    .rename_axis(columns=None)
    .reset_index()
)

# ============================================================================
# Block 10  10. Complex WHERE + FORMAT + LABEL
# Risk       : LOW
# SAS lines  : 11
# Status     : PARTIAL
# Syntax OK  : False  error: line 8: unterminated string literal (detected at line 8)
# Confidence : 0.50
# Latency    : 28.2s
# Tokens     : 2366  (318 prompt + 2048 completion)
# tok/s      : 73
# Z3 status  : unverifiable
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

{
  "python_code": "import pandas as pd\nimport numpy as np\n\n# Apply WHERE clause filtering\nmask = (\n    survey['age'].between(18, 65) &\n    survey['status'].isin(['ACTIVE', 'PENDING']) &\n    survey['score'].notna()  # score ^= . means score is not missing\n)\nreport = survey.loc[mask].copy()\n\n# SAS formats control display; pandas doesn't have a direct equivalent.\n# We round the column to mimic the 8.2 format display.\nreport['score'] = report['score'].round(2)\n\n# Ensure survey_date is a datetime object to mimic SAS date formatting\nreport['survey_date'] = pd.to_datetime(report['survey_date'], errors='coerce')\n\n# SAS labels are metadata for reporting; pandas doesn't have a built-in label system\n# separate from column names. They are noted here for reference:\n# score = 'Survey Score (0-100)'\n# survey_date = 'Date of Survey'\n\n# New column calculation\nreport['score_pct'] = report['score'] / 100",
  "imports_detected": [
    "import pandas as pd",
    "import numpy as np"
  ],
  "confidence": 0.95,
  "notes": "SAS formats and labels do not have direct pandas equivalents; rounding and datetime conversion are used to approximate format behavior
