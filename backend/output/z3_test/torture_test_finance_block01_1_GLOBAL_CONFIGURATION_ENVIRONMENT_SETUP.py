"""
SAS-to-Python translation: Configuration & Setup Block
Source: SAS macro variables, LIBNAME, FILENAME, OPTIONS statements
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
import os
from datetime import date
from pathlib import Path
from typing import Dict, Optional

# =============================================================================
# MACRO VARIABLES → Python Variables
# =============================================================================
# SAS: %LET env = PRODUCTION;
env: str = "PRODUCTION"

# SAS: %LET process_date = %SYSFUNC(today(), date9.);
# date9. format = DDMMMYYYY (e.g., 01JAN2025)
# Using Python date object; format for display as needed
process_date: date = date.today()
process_date_formatted: str = process_date.strftime("%d%b%Y").upper()  # e.g., "01JAN2025"

# SAS: %LET threshold = 5000;
threshold: int = 5000

# =============================================================================
# LIBNAME STATEMENTS → Data Path Configuration
# =============================================================================
# SAS LIBNAME creates librefs that map to physical directories
# Translating to a configuration class for clarity and reusability

class DataLibraries:
    """Configuration for data library paths (equivalent to SAS LIBNAME statements)."""
    
    # SAS: LIBNAME raw_src "/data/raw/source_systems";
    raw_src: Path = Path("/data/raw/source_systems")
    
    # SAS: LIBNAME staging "/data/staging/temp_storage";
    staging: Path = Path("/data/staging/temp_storage")
    
    # SAS: LIBNAME final "/data/production/final_tables";
    final: Path = Path("/data/production/final_tables")
    
    @classmethod
    def ensure_paths_exist(cls) -> None:
        """Create directories if they don't exist (similar to sashelp class)."""
        for libref, path in [
            ("raw_src", cls.raw_src),
            ("staging", cls.staging),
            ("final", cls.final)
        ]:
            path.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def to_dict(cls) -> Dict[str, Path]:
        """Return all library paths as a dictionary (like SAS dictionary.tables)."""
        return {
            "raw_src": cls.raw_src,
            "staging": cls.staging,
            "final": cls.final
        }


# =============================================================================
# FILENAME STATEMENT → File Path Configuration
# =============================================================================
# SAS: FILENAME log_out "/logs/migration_audit.txt";

log_out: Path = Path("/logs/migration_audit.txt")

# Ensure parent directory exists
log_out.parent.mkdir(parents=True, exist_ok=True)

# =============================================================================
# OPTIONS STATEMENT → Python Configuration Flags
# =============================================================================
# SAS: OPTIONS NODATE NONUMBER MPRINT;
# These are global options that affect SAS output behavior

class SASOptions:
    """
    Python equivalents for SAS OPTIONS settings.
    NODATE: Suppress date printing in output
    NONUMBER: Suppress page number printing
    MPRINT: Print macro expansion (debugging aid)
    """
    NODATE: bool = True      # Suppress date in output
    NONUMBER: bool = True    # Suppress page numbers
    MPRINT: bool = False     # Macro expansion tracing (off by default for performance)
    
    # MPRINT state for macro debugging
    _mprint_enabled: bool = False
    
    @classmethod
    def enable_mprint(cls) -> None:
        """Enable macro expansion tracing (SAS MPRINT)."""
        cls.MPRINT = True
        cls._mprint_enabled = True
    
    @classmethod
    def disable_mprint(cls) -> None:
        """Disable macro expansion tracing."""
        cls.MPRINT = False
        cls._mprint_enabled = False


# =============================================================================
# UTILITY: Load Data (Example Pattern for SAS Data Access)
# =============================================================================
def load_sas_dataset(
    libref: str,
    dataset: str,
    **kwargs
):
    """
    Load a SAS dataset from the configured library path.
    
    Parameters
    ----------
    libref : str
        Library reference name (e.g., 'raw_src', 'final')
    dataset : str
        Dataset name without .sas7bdat extension
    **kwargs : dict
        Additional arguments passed to pd.read_sas() or pd.read_csv()
    
    Returns
    -------
    pd.DataFrame or None
        Loaded dataframe, or None if file not found
    
    Notes
    -----
    Requires sas7bdat library for .sas7bdat files:
        pip install sas7bdat
    Alternative: Use pyreadstat for better performance:
        pip install pyreadstat
    """
    import pandas as pd
    
    # Map libref to path
    lib_map = DataLibraries.to_dict()
    if libref not in lib_map:
        raise ValueError(f"Unknown libref: {libref}. Valid: {list(lib_map.keys())}")
    
    file_path = lib_map[libref] / f"{dataset}.sas7bdat"
    
    try:
        # Try pyreadstat first (faster), fallback to pandas native
        try:
            import pyreadstat
            df, _ = pyreadstat.read_sas7bdat(file_path)
            return df
        except ImportError:
            return pd.read_sas(file_path, **kwargs)
    except FileNotFoundError:
        print(f"WARNING: File not found: {file_path}")
        return None


def write_sas_dataset(
    df,
    libref: str,
    dataset: str,
    **kwargs
) -> bool:
    """
    Write a DataFrame to a SAS dataset in the configured library path.
    
    Parameters
    ----------
    df : pd.DataFrame
        Data to write
    libref : str
        Library reference name
    dataset : str
        Dataset name without .sas7bdat extension
    **kwargs : dict
        Additional arguments for writer
    
    Returns
    -------
    bool
        True if successful, False otherwise
    """
    import pandas as pd
    
    lib_map = DataLibraries.to_dict()
    if libref not in lib_map:
        raise ValueError(f"Unknown libref: {libref}")
    
    file_path = lib_map[libref] / f"{dataset}.sas7bdat"
    
    try:
        df.to_sas(format='sas7bdat', **kwargs)
        return True
    except Exception as e:
        print(f"ERROR writing SAS dataset: {e}")
        return False


# =============================================================================
# LOGGER SETUP (Equivalent to FILENAME log_out)
# =============================================================================
import logging

# Configure logging to file (equivalent to FILENAME log_out)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_out),
        logging.StreamHandler()  # Also print to console
    ]
)

logger: logging.Logger = logging.getLogger(__name__)


# =============================================================================
# VERIFICATION: Print Configuration Summary
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("SAS Configuration Translated to Python")
    print("=" * 60)
    print(f"Environment:        {env}")
    print(f"Process Date:        {process_date} (formatted: {process_date_formatted})")
    print(f"Threshold:           {threshold}")
    print("-" * 60)
    print("Library Paths:")
    for name, path in DataLibraries.to_dict().items():
        exists = "✓" if path.exists() else "✗ (not found)"
        print(f"  {name:12} = {path}  {exists}")
    print("-" * 60)
    print(f"Log File:            {log_out}")
    print(f"  Parent exists:     {log_out.parent.exists()}")
    print(f"Options: NODATE={SASOptions.NODATE}, NONUMBER={SASOptions.NONUMBER}, MPRINT={SASOptions.MPRINT}")
    print("=" * 60)
