"""QueryGenerator — Generate stratified ablation queries from partitions.

Produces 10 queries per file, stratified across LOW/MODERATE/HIGH complexity.
Each query targets a specific partition_type and uses template-based query text.
"""

from __future__ import annotations

import random
from uuid import uuid4

import structlog

log = structlog.get_logger(__name__)

QUERY_TEMPLATES: dict[str, list[str]] = {
    "DATA_STEP_BASIC": [
        "Convert SAS DATA step with assignment and keep/drop to Python pandas",
        "Translate SAS DATA step if/else logic to Python",
    ],
    "DATA_STEP_MERGE": [
        "Convert SAS MERGE BY statement to Python pandas merge",
        "Translate SAS one-to-many merge to Python",
    ],
    "DATA_STEP_RETAIN": [
        "Convert SAS RETAIN with running total to Python cumulative sum",
        "Translate SAS lag pattern to Python shift operation",
    ],
    "DATA_STEP_ARRAY": [
        "Convert SAS ARRAY with DO OVER to Python list comprehension",
        "Translate SAS multi-dimensional array to Python numpy",
    ],
    "DATA_STEP_FIRST_LAST": [
        "Convert SAS FIRST.var / LAST.var BY-group processing to Python groupby",
        "Translate SAS FIRST/LAST flags to pandas groupby head/tail",
    ],
    "DATE_ARITHMETIC": [
        "Convert SAS INTNX INTCK date functions to Python pandas DateOffset",
        "Translate SAS MDY TODAY date creation to Python datetime",
    ],
    "PROC_SQL": [
        "Convert SAS PROC SQL with JOIN and subquery to Python pandas",
        "Translate SAS PROC SQL GROUP BY HAVING to Python",
    ],
    "PROC_MEANS": [
        "Convert SAS PROC MEANS with CLASS VAR OUTPUT OUT to Python groupby agg",
        "Translate SAS PROC MEANS NWAY to Python pandas",
    ],
    "PROC_FREQ": [
        "Convert SAS PROC FREQ cross-tabulation to Python pandas crosstab",
        "Translate SAS PROC FREQ chi-square to Python scipy",
    ],
    "MACRO_BASIC": [
        "Convert SAS %MACRO %MEND %LET to Python function",
        "Translate SAS macro parameters to Python function arguments",
    ],
    "MACRO_CONDITIONAL": [
        "Convert SAS %IF %THEN %ELSE to Python if/else",
        "Translate nested SAS %DO %END to Python loop",
    ],
    "PROC_SORT": [
        "Convert SAS PROC SORT BY NODUPKEY to Python sort_values drop_duplicates",
        "Translate SAS PROC SORT descending to Python pandas",
    ],
    "PROC_REG_LOGISTIC": [
        "Convert SAS PROC REG MODEL to Python statsmodels OLS",
        "Translate SAS PROC LOGISTIC to Python sklearn LogisticRegression",
    ],
    "PROC_IMPORT_EXPORT": [
        "Convert SAS PROC IMPORT DBMS CSV to Python pandas read_csv",
        "Translate SAS INFILE INPUT to Python file reading",
    ],
    "MISSING_VALUE_HANDLING": [
        "Convert SAS NMISS CMISS missing value handling to Python isna",
        "Translate SAS missing value dot comparison to Python NaN check",
    ],
}


def generate_queries(
    partitions: list[dict],
    n_per_file: int = 10,
    seed: int = 42,
) -> list[dict]:
    """Generate ablation queries from partition data.

    Args:
        partitions: List of PartitionIR dicts with partition_type, complexity_tier.
        n_per_file: Number of queries per file.
        seed: Random seed for reproducibility.

    Returns:
        List of query dicts with query_text, expected_type, complexity_tier.
    """
    rng = random.Random(seed)
    queries: list[dict] = []

    # Group by file
    by_file: dict[str, list[dict]] = {}
    for p in partitions:
        fid = p.get("source_file_id", p.get("file_id", "unknown"))
        by_file.setdefault(fid, []).append(p)

    for file_id, file_parts in by_file.items():
        # Stratified sample
        by_tier: dict[str, list[dict]] = {"LOW": [], "MODERATE": [], "HIGH": []}
        for p in file_parts:
            tier = p.get("complexity_tier", "LOW")
            if tier in by_tier:
                by_tier[tier].append(p)

        selected: list[dict] = []
        for tier, parts in by_tier.items():
            n_take = max(1, round(n_per_file * len(parts) / max(len(file_parts), 1)))
            selected.extend(rng.sample(parts, min(n_take, len(parts))))

        while len(selected) < n_per_file and file_parts:
            selected.append(rng.choice(file_parts))
        selected = selected[:n_per_file]

        for p in selected:
            ptype = p.get("partition_type", "DATA_STEP_BASIC")
            templates = QUERY_TEMPLATES.get(ptype, ["Convert this SAS code to Python"])
            query_text = rng.choice(templates)

            queries.append(
                {
                    "query_id": str(uuid4()),
                    "file_id": file_id,
                    "partition_id": p.get("partition_id", p.get("block_id", "")),
                    "query_text": query_text,
                    "expected_partition_type": ptype,
                    "complexity_tier": p.get("complexity_tier", "LOW"),
                    "expected_category": ptype,
                }
            )

    log.info("queries_generated", total=len(queries))
    return queries
