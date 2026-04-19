import pandas as pd

# Assuming 'transactions' DataFrame is already loaded in the environment.
# This translation handles the SAS DATA step pattern:
#   BY customer_id processing with RETAIN, FIRST./LAST. logic

# Ensure data is sorted by customer_id (SAS BY processing requires sorted data)
df = transactions.sort_values('customer_id').reset_index(drop=True)

# Create first/last flags for customer_id detection
# FIRST.var = 1 when current row is first in BY group
df['_is_first'] = df.groupby('customer_id').cumcount() == 0
# LAST.var = 1 when current row is last in BY group
df['_is_last'] = df.groupby('customer_id').cumcount(ascending=False) == 0

# Calculate running_total: cumulative sum of 'amount' within each customer group
# This implicitly resets at the start of each group (equivalent to SAS RETAIN reset)
df['running_total'] = df.groupby('customer_id')['amount'].cumsum()

# Calculate tx_count: row number within each customer group (1-based)
df['tx_count'] = df.groupby('customer_id').cumcount() + 1

# Output only the last row per customer_id (equivalent to SAS 'if last.customer_id then output;')
customer_summary = df[df['_is_last']][['customer_id', 'running_total', 'tx_count']].copy()

# Clean up temporary flags
df.drop(columns=['_is_first', '_is_last'], inplace=True)

# Result: customer_summary contains one row per customer with:
#   - customer_id
#   - running_total: sum of all transaction amounts for that customer
#   - tx_count: total number of transactions for that customer
