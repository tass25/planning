import pandas as pd

# Read input data — replace with actual source (e.g., pd.read_csv, database connection)
customers = pd.read_csv('customers.csv')  # <-- substitute with real data load

# PROC SORT data=customers NODUPKEY; by customer_id;
# Step 1: Sort by customer_id (SAS always sorts before nodupkey removal)
customers = customers.sort_values('customer_id')

# Step 2: Remove duplicate customer_id values, keeping the first occurrence
# This mimics SAS NODUPKEY behavior exactly
customers = customers.drop_duplicates(subset=['customer_id'], keep='first')
