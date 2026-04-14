import pandas as pd
import numpy as np


def preprocess_finance_data(in_ds, out_ds):
    """
    Translates SAS macro preprocess_finance_data.
    
    Processing steps:
    1. Clean customer_name: STRIP whitespace + UPCASE uppercase
    2. Remove hyphens from account_id using COMPRESS(str, chars) 2-arg form
    3. Set status and flag based on balance (IF/THEN/ELSE logic)
    4. Calculate days_since_active as today() - last_transaction_dt
    5. Classify account_type based on days_since_active
    6. Add column labels (stored as comments/metadata)
    7. Sort: BY account_id ASCENDING, days_since_active DESCENDING
    """
    # Create a copy to avoid mutating the input
    df = in_ds.copy()
    
    # String transformations
    # UPCASE(STRIP(name)) -> strip whitespace, then convert to uppercase
    df['customer_name'] = df['name'].str.strip().str.upper()
    
    # COMPRESS(account_id, '-') -> 2-arg form removes ONLY hyphens
    # Convert to string first in case account_id is numeric
    df['account_id'] = df['account_id'].astype(str).str.replace('-', '', regex=False)
    
    # IF/THEN/ELSE logic for status and flag based on balance
    # SAS: IF balance < 0 THEN DO; status = 'OVERDRAWN'; flag = 1; END;
    #      ELSE IF balance = 0 THEN status = 'EMPTY';
    #      ELSE status = 'ACTIVE';
    conditions_status = [
        df['balance'] < 0,
        df['balance'] == 0
    ]
    choices_status = [
        'OVERDRAWN',
        'EMPTY'
    ]
    df['status'] = np.select(conditions_status, choices_status, default='ACTIVE')
    
    # flag = 1 only when balance < 0
    df['flag'] = np.where(df['balance'] < 0, 1, 0)
    
    # Calculate days since last transaction
    # today() returns current date, subtract last_transaction_dt
    today = pd.Timestamp('today').normalize()
    df['days_since_active'] = (today - df['last_transaction_dt']).dt.days
    
    # IF days_since_active > 365 THEN account_type = 'DORMANT'
    # ELSE account_type = 'CURRENT'
    df['account_type'] = np.where(
        df['days_since_active'] > 365,
        'DORMANT',
        'CURRENT'
    )
    
    # SAS Labels (pandas doesn't have native column labels, stored as metadata)
    # LABEL status = "Account Status Indicator"
    #       account_type = "Activity Classification"
    column_labels = {
        'status': 'Account Status Indicator',
        'account_type': 'Activity Classification'
    }
    
    # PROC SORT: BY account_id DESCENDING days_since_active
    # CRITICAL: SAS BY a DESCENDING b means a ascending, b descending
    # -> sort_values(['a', 'b'], ascending=[True, False])
    df = df.sort_values(
        ['account_id', 'days_since_active'],
        ascending=[True, False]
    )
    
    # DATA out_ds (DROP=err_code) - remove err_code column if present
    # Note: err_code is not created in this step, but DROP= ensures it's excluded if present
    if 'err_code' in df.columns:
        df = df.drop(columns=['err_code'])
    
    # Assign to out_ds (simulating DATA step output)
    out_ds = df
    
    return out_ds


# Example usage demonstration
if __name__ == "__main__":
    # Create sample input data
    sample_data = pd.DataFrame({
        'name': ['  john doe  ', 'Jane Smith', 'Bob   '],
        'account_id': ['ACC-123-456', '789', 'ACC-001'],
        'balance': [-100.50, 0, 1500.00],
        'last_transaction_dt': pd.to_datetime([
            '2022-01-15', '2024-06-01', '2024-11-20'
        ])
    })
    
    print("Input DataFrame:")
    print(sample_data)
    print("\n" + "="*60 + "\n")
    
    # Process the data
    result = preprocess_finance_data(sample_data, pd.DataFrame())
    
    print("Output DataFrame:")
    print(result)
