import pandas as pd
import numpy as np


def get_high_value_customers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Translate SAS PROC SQL: inner join with avg subquery, filter on 1.5x threshold.
    
    SAS Logic:
    1. Calculate mean(amount) grouped by customer_id
    2. Inner join back to transactions on customer_id
    3. Keep rows where t.amount > avg_t.avg_amount * 1.5
    """
    # Handle empty DataFrame edge case
    if df.empty:
        return pd.DataFrame(columns=['customer_id', 'amount', 'avg_amount'])
    
    # Subquery: calculate average amount per customer
    # dropna=False replicates SAS GROUP BY behavior (NaN kept as group)
    avg_by_customer = (
        df.groupby('customer_id', dropna=False)['amount']
        .mean()
        .reset_index()
        .rename(columns={'amount': 'avg_amount'})
    )
    
    # Inner join - merge only matches (equivalent to SAS INNER JOIN)
    merged = df.merge(avg_by_customer, on='customer_id', how='inner')
    
    # Filter: keep only high-value transactions (amount > 1.5 * avg_amount)
    high_value = merged[merged['amount'] > merged['avg_amount'] * 1.5]
    
    return high_value[['customer_id', 'amount', 'avg_amount']]


# Example usage (assumes transactions DataFrame is already loaded):
# high_value = get_high_value_customers(transactions)
