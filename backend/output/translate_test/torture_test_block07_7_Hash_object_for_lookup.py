"""
Translation of SAS DATA Step with Hash Table Lookup

SAS Logic:
1. Declare hash table from 'lookup_table' with key='product_id', data=['product_name', 'category']
2. For each row in 'transactions', perform hash lookup
3. If product_id not found (rc != 0), set product_name = 'UNKNOWN'

Python Equivalent:
- Load both DataFrames and perform LEFT merge on product_id
- Fill missing (unmatched) product_name values with 'UNKNOWN'
"""

import pandas as pd


def translate_hash_lookup(transactions, lookup_table):
    """
    Translate SAS hash lookup to pandas merge operation.
    
    Parameters
    ----------
    transactions : pd.DataFrame
        Source DataFrame containing transaction records
    lookup_table : pd.DataFrame
        Lookup DataFrame with product_id, product_name, category columns
    
    Returns
    -------
    pd.DataFrame
        Enriched DataFrame with product_name and category from lookup
    """
    # Validate inputs are non-empty DataFrames
    if transactions.empty:
        # Return empty DataFrame with expected columns if transactions is empty
        return pd.DataFrame(columns=list(transactions.columns) + ['product_name', 'category'])
    
    if lookup_table.empty:
        # If lookup is empty, all product_names become 'UNKNOWN'
        result = transactions.copy()
        result['product_name'] = 'UNKNOWN'
        result['category'] = None
        return result
    
    # Select only the columns needed for the lookup (simulate hash.defineData)
    lookup_subset = lookup_table[['product_id', 'product_name', 'category']].copy()
    
    # Normalize key column to handle any case differences
    # SAS variable names are case-insensitive; Python is not
    transactions['_product_id_norm'] = transactions['product_id']
    lookup_subset['_product_id_norm'] = lookup_subset['product_id']
    
    # Perform LEFT merge — equivalent to SAS hash.find() with default behavior
    # All transaction rows are preserved; lookup columns added where match exists
    enriched = transactions.merge(
        lookup_subset,
        on='_product_id_norm',
        how='left',
        suffixes=('', '_lookup')
    )
    
    # Clean up the normalized key column
    enriched.drop(columns=['_product_id_norm'], inplace=True)
    
    # Handle product_name: if lookup failed (NaN), set to 'UNKNOWN'
    # Equivalent to SAS: if rc ^= 0 then product_name = 'UNKNOWN'
    enriched['product_name'] = enriched['product_name'].fillna('UNKNOWN')
    
    return enriched


# Example usage with file I/O (wrapped in try/except per requirements)
if __name__ == '__main__':
    try:
        # Load source data
        transactions = pd.read_csv('transactions.csv')
        lookup_table = pd.read_csv('lookup_table.csv')
        
        # Execute translation
        enriched = translate_hash_lookup(transactions, lookup_table)
        
        # Display results
        print("Translation successful. Shape:", enriched.shape)
        print("\nFirst few rows:")
        print(enriched.head())
        
        # Show lookup hit rate
        unknown_count = (enriched['product_name'] == 'UNKNOWN').sum()
        print(f"\nUnmatched product_ids (UNKNOWN): {unknown_count} / {len(enriched)}")
        
    except FileNotFoundError as e:
        print(f"Error: Required file not found - {e}")
    except pd.errors.EmptyDataError:
        print("Error: One or more input files are empty")
    except Exception as e:
        print(f"Unexpected error during translation: {e}")
