# Codara  --  Model Benchmark

**Run:** 2026-04-15T21:20:50Z
**SAS file:** torture_test.sas  (10 blocks)
**Models:** minimax-m2.7:cloud, qwen3-coder-next, deepseek-v3.2, nemotron-3-super:cloud

---

## 1. Aggregate

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Success rate | 100% | 0% | 0% | 100% |
| Syntax valid | 100% | 0% | 0% | 100% |
| Mean confidence | 0.94 | 0.00 | 0.00 | 0.93 |
| Mean latency (s) | 16.7 | 2.1 | 2.0 | 6.8 |
| p95 latency (s) | 34.0 | 2.1 | 2.1 | 12.0 |
| Total time (s) | 167 | 21 | 20 | 68 |
| Prompt tokens (total) | 3,242 | 0 | 0 | 3,379 |
| Completion tokens | 7,025 | 0 | 0 | 2,389 |
| Total tokens | 10,267 | 0 | 0 | 5,768 |
| Mean tok/s | 52 | 0 | 0 | 41 |
| Z3 formally proved | 3/10 | 0/10 | 0/10 | 3/10 |
| Z3 counterexamples | 0/10 | 0/10 | 0/10 | 0/10 |
| Z3 unknown | 7/10 | 0/10 | 0/10 | 7/10 |

---

## 2. Block-by-Block

### Block 1: 1. RETAIN + BY-group FIRST./LAST.
Risk: HIGH | SAS lines: 12

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 10.1 | 2.1 | 2.0 | 3.7 |
| Prompt tokens | 325 | 0 | 0 | 336 |
| Compl. tokens | 649 | 0 | 0 | 176 |
| tok/s | 64 | 0 | 0 | 48 |
| Confidence | 0.95 | 0.00 | 0.00 | 0.95 |
| Python LOC | 12 | 0 | 0 | 7 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | unknown | skipped | skipped | unknown |
| Z3 pattern | conditional_assignment | - | - | conditional_assignment |
| Z3 lat (ms) | 172.0 | 0.0 | 0.0 | 0.0 |

### Block 2: 2. Missing value logic (SAS . < any number)
Risk: LOW | SAS lines: 7

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 11.6 | 2.0 | 2.1 | 5.8 |
| Prompt tokens | 306 | 0 | 0 | 321 |
| Compl. tokens | 820 | 0 | 0 | 176 |
| tok/s | 71 | 0 | 0 | 30 |
| Confidence | 0.95 | 0.00 | 0.00 | 0.95 |
| Python LOC | 11 | 0 | 0 | 11 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | unknown | skipped | skipped | unknown |
| Z3 pattern | boolean_filter | - | - | boolean_filter |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 3: 3. PROC SQL with correlated subquery
Risk: MOD | SAS lines: 14

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 10.5 | 2.1 | 2.1 | 4.0 |
| Prompt tokens | 344 | 0 | 0 | 355 |
| Compl. tokens | 775 | 0 | 0 | 209 |
| tok/s | 74 | 0 | 0 | 52 |
| Confidence | 0.95 | 0.00 | 0.00 | 0.95 |
| Python LOC | 12 | 0 | 0 | 9 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | unknown | skipped | skipped | unknown |
| Z3 pattern | boolean_filter | - | - | boolean_filter |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 16.0 |

### Block 4: 4. Macro with parameters + %DO loop
Risk: MOD | SAS lines: 14

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 14.0 | 2.1 | 2.0 | 10.2 |
| Prompt tokens | 380 | 0 | 0 | 396 |
| Compl. tokens | 1063 | 0 | 0 | 414 |
| tok/s | 76 | 0 | 0 | 41 |
| Confidence | 0.95 | 0.00 | 0.00 | 0.95 |
| Python LOC | 26 | 0 | 0 | 29 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | unknown | skipped | skipped | unknown |
| Z3 pattern | conditional_assignment | - | - | conditional_assignment |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 5: 5. PROC MEANS with CLASS and OUTPUT
Risk: LOW | SAS lines: 8

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 13.1 | 2.1 | 2.0 | 4.7 |
| Prompt tokens | 313 | 0 | 0 | 326 |
| Compl. tokens | 564 | 0 | 0 | 347 |
| tok/s | 43 | 0 | 0 | 74 |
| Confidence | 0.95 | 0.00 | 0.00 | 0.85 |
| Python LOC | 13 | 0 | 0 | 15 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | PROVED | skipped | skipped | PROVED |
| Z3 pattern | proc_means_groupby | - | - | proc_means_groupby |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 6: 6. PROC SORT NODUPKEY
Risk: LOW | SAS lines: 3

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 6.7 | 2.1 | 2.1 | 7.5 |
| Prompt tokens | 269 | 0 | 0 | 281 |
| Compl. tokens | 360 | 0 | 0 | 102 |
| tok/s | 54 | 0 | 0 | 14 |
| Confidence | 1.00 | 0.00 | 0.00 | 1.00 |
| Python LOC | 3 | 0 | 0 | 3 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | PROVED | skipped | skipped | PROVED |
| Z3 pattern | sort_nodupkey | - | - | sort_nodupkey |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 7: 7. Hash object for lookup
Risk: HIGH | SAS lines: 11

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 10.0 | 2.1 | 2.0 | 4.5 |
| Prompt tokens | 329 | 0 | 0 | 342 |
| Compl. tokens | 629 | 0 | 0 | 204 |
| tok/s | 63 | 0 | 0 | 45 |
| Confidence | 0.95 | 0.00 | 0.00 | 0.95 |
| Python LOC | 12 | 0 | 0 | 9 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | unknown | skipped | skipped | unknown |
| Z3 pattern | conditional_assignment | - | - | conditional_assignment |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 8: 8. Multi-level nested macro
Risk: MOD | SAS lines: 11

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 25.5 | 2.0 | 2.1 | 4.8 |
| Prompt tokens | 355 | 0 | 0 | 370 |
| Compl. tokens | 909 | 0 | 0 | 319 |
| tok/s | 36 | 0 | 0 | 67 |
| Confidence | 0.85 | 0.00 | 0.00 | 0.85 |
| Python LOC | 17 | 0 | 0 | 17 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | unknown | skipped | skipped | unknown |
| Z3 pattern | proc_means_groupby | - | - | proc_means_groupby |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 9: 9. PROC TRANSPOSE
Risk: LOW | SAS lines: 5

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 31.2 | 2.0 | 2.0 | 10.4 |
| Prompt tokens | 285 | 0 | 0 | 296 |
| Compl. tokens | 588 | 0 | 0 | 171 |
| tok/s | 19 | 0 | 0 | 16 |
| Confidence | 0.95 | 0.00 | 0.00 | 0.95 |
| Python LOC | 6 | 0 | 0 | 7 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | unknown | skipped | skipped | unknown |
| Z3 pattern | - | - | - | - |
| Z3 lat (ms) | 0.0 | 0.0 | 0.0 | 0.0 |

### Block 10: 10. Complex WHERE + FORMAT + LABEL
Risk: LOW | SAS lines: 11

| Metric | minimax | qwen3 | deepseek-v3.2 | nemotron |
|--------|----|----|----|----|
| Status | SUCCESS | PARTIAL | PARTIAL | SUCCESS |
| Latency (s) | 34.0 | 2.0 | 2.1 | 12.0 |
| Prompt tokens | 336 | 0 | 0 | 356 |
| Compl. tokens | 668 | 0 | 0 | 271 |
| tok/s | 20 | 0 | 0 | 23 |
| Confidence | 0.95 | 0.00 | 0.00 | 0.95 |
| Python LOC | 14 | 0 | 0 | 16 |
| Syntax valid | yes | NO:  | NO:  | yes |
| Z3 result | PROVED | skipped | skipped | PROVED |
| Z3 pattern | boolean_filter | - | - | boolean_filter |
| Z3 lat (ms) | 15.0 | 0.0 | 0.0 | 0.0 |

---

## 3. Translation snippets (first 12 lines)

### Block 1: 1. RETAIN + BY-group FIRST./LAST.

**minimax**
```python
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
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd
import numpy as np

# Assuming 'transactions' DataFrame is already loaded
customer_summary = transactions.sort_values(['customer_id']).groupby('customer_id', as_index=False).agg(
    running_total=('amount', 'sum'),
    tx_count=('amount', 'size')
)
```

### Block 2: 2. Missing value logic (SAS . < any number)

**minimax**
```python
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
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
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
```

### Block 3: 3. PROC SQL with correlated subquery

**minimax**
```python
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
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd
import numpy as np

# Assuming 'transactions' DataFrame exists
# Compute average amount per customer
avg_t = transactions.groupby('customer_id', as_index=False)['amount'].mean().rename(columns={'amount': 'avg_amount'})

# Join with original transactions
high_value = pd.merge(transactions, avg_t, on='customer_id', how='inner')

# Filter rows where amount > 1.5 * avg_amount
high_value = high_value[high_value['amount'] > high_value['avg_amount'] * 1.5][['customer_id', 'amount', 'avg_amount']].copy()
```

### Block 4: 4. Macro with parameters + %DO loop

**minimax**
```python
import pandas as pd

def rolling_mean(dsn, var, window=3, out=None):
    """
    Calculate rolling mean using circular buffer (SAS macro equivalent).
    
    Parameters:
    - dsn: DataFrame or path to CSV/SAS file
    - var: variable name to calculate rolling mean on
    - window: window size (default 3)
    - out: output file path (optional)
    
# ... 14 more lines
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd
import numpy as np

def rolling_mean(dsn, var, window=3, out=None):
    """
    Compute rolling mean of a variable using a temporary array approach similar to SAS.
    This mimics the SAS macro: retains a circular buffer of size `window` and computes
    the mean only when at least `window` observations are available.
    """
    df = dsn.copy()
    # Initialize circular buffer and index
    vals = [np.nan] * window
# ... 17 more lines
```

### Block 5: 5. PROC MEANS with CLASS and OUTPUT

**minimax**
```python
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
# ... 1 more lines
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd
import numpy as np

# Assuming 'sales' DataFrame is already loaded
# PROC MEANS with CLASS and VAR -> groupby + agg
summary = sales.groupby(['region', 'product_line'], dropna=False).agg(
    avg_revenue=('revenue', 'mean'),
    avg_units=('units_sold', 'mean'),
    total_revenue=('revenue', 'sum'),
    total_units=('units_sold', 'sum'),
    obs_count=('revenue', 'size')  # 'n' in SAS = count of non-missing; size counts all rows including NaN in group
).reset_index()
# ... 3 more lines
```

### Block 6: 6. PROC SORT NODUPKEY

**minimax**
```python
import pandas as pd

# Remove duplicate customer_ids, keeping first occurrence
customers = customers.drop_duplicates(subset=['customer_id'], keep='first')
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd

# Assuming 'customers' is a pandas DataFrame
customers = customers.sort_values('customer_id').drop_duplicates(subset=['customer_id'])
```

### Block 7: 7. Hash object for lookup

**minimax**
```python
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
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd
import numpy as np

# Load lookup table and transactions
h = pd.read_csv('lookup_table.csv')
transactions = pd.read_csv('transactions.csv')

# Perform left join to enrich transactions with product details
enriched = pd.merge(transactions, h[['product_id', 'product_name', 'category']], on='product_id', how='left')

# Replace missing product_name with 'UNKNOWN'
enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')
```

### Block 8: 8. Multi-level nested macro

**minimax**
```python
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
# ... 5 more lines
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd
import numpy as np

# Assuming datasets are already loaded as DataFrames in the environment
# Replace these with actual DataFrame loading if needed (e.g., pd.read_csv)
sales = pd.DataFrame()  # Placeholder
returns = pd.DataFrame()  # Placeholder
inventory = pd.DataFrame()  # Placeholder

def summarise(dsn):
    # PROC MEANS with no VAR statement defaults to all numeric columns
    # Using describe() for summary statistics (count, mean, std, min, 25%, 50%, 75%, max)
# ... 5 more lines
```

### Block 9: 9. PROC TRANSPOSE

**minimax**
```python
import pandas as pd

# PROC TRANSPOSE equivalent: pivot from long to wide format
wide_sales = monthly_sales.pivot(index='product_id', columns='month', values='revenue')
# Add SAS-style prefix to column names
wide_sales.columns = [f'month_{col}' for col in wide_sales.columns]
wide_sales = wide_sales.reset_index()
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd

# Transpose monthly_sales from long to wide format, with product_id as index and month as columns
wide_sales = monthly_sales.pivot(index='product_id', columns='month', values='revenue')
# Rename columns to add prefix 'month_'
wide_sales.columns = [f'month_{col}' for col in wide_sales.columns]
# Reset index to make product_id a column again
wide_sales = wide_sales.reset_index()
```

### Block 10: 10. Complex WHERE + FORMAT + LABEL

**minimax**
```python
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
# ... 2 more lines
```

**qwen3**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'qwen3-coder-next' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**deepseek-v3.2**
```python
# PARTIAL: Error code: 404 - {'error': {'message': "model 'deepseek-v3.2' not found", 'type': 'not_found_error', 'param': None, 'code': None}}
```

**nemotron**
```python
import pandas as pd
import numpy as np

# Assuming 'survey' DataFrame is already defined
report = survey[
    (survey['age'] >= 18) & 
    (survey['age'] <= 65) & 
    (survey['status'].isin(['ACTIVE', 'PENDING'])) & 
    (survey['score'].notna())
].copy()

report['score'] = report['score'].round(2)
# ... 4 more lines
```
