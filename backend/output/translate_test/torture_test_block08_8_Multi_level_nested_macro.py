"""
SAS Macro Translation: apply_to_all and summarise

Translation of:
%macro apply_to_all(action=, datasets=);
    %let n = %sysfunc(countw(&datasets));
    %do i = 1 %to &n;
        %let ds = %scan(&datasets, &i);
        %&action(dsn=&ds);
    %end;
%mend;

%macro summarise(dsn=);
    proc means data=&dsn; run;
%mend;

%apply_to_all(action=summarise, datasets=sales returns inventory);
"""

import pandas as pd


def summarise(dsn):
    """
    Generate PROC MEANS-style summary statistics for a dataset.
    
    PROC MEANS in SAS:
    - Operates on all numeric variables by default
    - Excludes missing values per variable (not per row)
    - Outputs: N, Mean, Std Dev, Minimum, Maximum
    
    Args:
        dsn: Dataset name (string) - will load from '{dsn}.csv'
    
    Raises:
        FileNotFoundError: If dataset CSV does not exist
        ValueError: If no numeric columns found
    """
    # Load dataset from CSV (following pattern: dataset_name = pd.read_csv('dataset_name.csv'))
    csv_path = f"{dsn}.csv"
    
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Dataset '{dsn}' not found. Expected file: {csv_path}")
    
    # SAS is case-insensitive; normalize column names to lowercase
    df.columns = df.columns.str.lower()
    
    # Select only numeric columns (PROC MEANS operates on numeric vars by default)
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    
    if not numeric_cols:
        raise ValueError(f"No numeric columns found in dataset '{dsn}'")
    
    # Build summary statistics matching PROC MEANS output exactly
    # SAS excludes NAs per variable - use .dropna() per column during aggregation
    results = []
    for var in numeric_cols:
        var_data = df[var].dropna()  # Exclude NAs per variable (like SAS)
        
        summary = {
            'Variable': var,
            'N': len(var_data),  # Count excludes NaN
            'Mean': var_data.mean(),
            'Std Dev': var_data.std(ddof=1),  # SAS uses sample std (ddof=1)
            'Minimum': var_data.min(),
            'Maximum': var_data.max()
        }
        results.append(summary)
    
    summary_df = pd.DataFrame(results)
    
    # Print summary (SAS PROC MEANS prints to output by default)
    print(f"===== Summary Statistics for {dsn} =====")
    print(summary_df.to_string(index=False))
    print()
    
    return summary_df


def apply_to_all(action, datasets):
    """
    Apply an action function to each dataset name in a space-separated string.
    
    Translation of SAS macro:
    %macro apply_to_all(action=, datasets=);
        %let n = %sysfunc(countw(&datasets));
        %do i = 1 %to &n;
            %let ds = %scan(&datasets, &i);
            %&action(dsn=&ds);
        %end;
    %mend;
    
    Args:
        action: Function that accepts 'dsn' keyword argument
        datasets: Space-separated string of dataset names
    """
    # Split datasets by whitespace (matching SAS %scan with default delimiter)
    dataset_list = datasets.split()
    
    for ds in dataset_list:
        # Call the action function with dsn parameter (matching SAS macro call)
        action(dsn=ds)


# Execute the equivalent of:
# %apply_to_all(action=summarise, datasets=sales returns inventory);
if __name__ == "__main__":
    try:
        apply_to_all(action=summarise, datasets="sales returns inventory")
    except FileNotFoundError as e:
        print(f"Error: {e}")
        print("Note: Ensure CSV files exist for each dataset name in the datasets list.")
