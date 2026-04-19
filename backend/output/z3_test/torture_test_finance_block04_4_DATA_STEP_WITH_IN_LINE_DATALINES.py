import pandas as pd
import io

# Inline data equivalent to SAS DATALINES
data = """Account_ID,Adjustment_Amt,Type
ACC100,250.00,REBATE
ACC205,-50.25,FEE
ACC309,1000.00,BONUS
ACC412,-15.00,CHARGE"""

df = pd.read_csv(io.StringIO(data))
# Ensure numeric column is float type (SAS default for numeric)
df['Adjustment_Amt'] = df['Adjustment_Amt'].astype(float)