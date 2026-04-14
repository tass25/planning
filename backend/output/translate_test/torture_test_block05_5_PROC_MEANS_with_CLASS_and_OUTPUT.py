
import pandas as pd

# Load sales data (adjust path as needed)
# sales = pd.read_csv('sales.csv')  # or read from another source

# PROC MEANS equivalent:
# - CLASS region product_line  → groupby(['region', 'product_line'], dropna=False)
# - noprint                     → no console output needed
# - mean=avg_revenue avg_units  → mean aggregation for revenue and units_sold
# - sum=total_revenue total_units → sum aggregation
# - n=obs_count                 → count (non-missing) aggregation
# - drop=_type_ _freq_           → these are SAS-generated variables, no pandas equivalent needed

summary = (
    sales
    .groupby(['region', 'product_line'], dropna=False)
    .agg(
        avg_revenue=('revenue', 'mean'),
        avg_units=('units_sold', 'mean'),
        total_revenue=('revenue', 'sum'),
        total_units=('units_sold', 'sum'),
        obs_count=('revenue', 'count')  # n= counts non-missing observations
    )
    .reset_index()
)
