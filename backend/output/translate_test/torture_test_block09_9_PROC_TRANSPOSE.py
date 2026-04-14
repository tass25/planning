import pandas as pd

# Load input data from CSV
monthly_sales = pd.read_csv('monthly_sales.csv')

# Normalize column names to lowercase for case-insensitive SAS equivalence
monthly_sales.columns = monthly_sales.columns.str.lower()

# Use pd.pivot() instead of pd.pivot_table() to avoid aggregation
# SAS PROC TRANSPOSE does NOT aggregate duplicates; it errors on them
# pd.pivot() raises ValueError on duplicate entries, which matches SAS behavior
# If duplicates may exist, they must be deduplicated beforehand
wide_sales = monthly_sales.pivot(
    index='product_id',   # BY variable in SAS TRANSPOSE
    columns='month',      # ID variable - each unique value becomes a column
    values='revenue'      # VAR variable - values to transpose
)

# Add prefix to column names (SAS: prefix=month_)
wide_sales.columns = ['month_' + str(col) for col in wide_sales.columns]

# Reset index to make product_id a regular column (SAS output structure)
wide_sales = wide_sales.reset_index()

# Store result silently - do not print (SAS out= dataset behavior)
wide_sales