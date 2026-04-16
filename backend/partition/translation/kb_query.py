"""Knowledge Base retrieval for translation context.

Queries LanceDB with filtering by partition_type, failure_mode,
and target_runtime.

Hybrid retrieval: blends semantic cosine (Nomic 768-dim) with
keyword-TF cosine on SAS-specific vocabulary.

    score = KEYWORD_WEIGHT * keyword_cosine + SEMANTIC_WEIGHT * semantic_cosine

This improves recall for structurally similar SAS patterns that may not
be semantically close in embedding space (e.g., two different PROC SORT
variants that share many SAS keywords but differ in business meaning).
"""

from __future__ import annotations

import re
from typing import Optional

import lancedb
import structlog

logger = structlog.get_logger()

# Only allow safe identifier characters in WHERE clause values.
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_. -]+$")

# Module-level singleton: one LanceDB connection per db_path.
_db_connections: dict[str, lancedb.DBConnection] = {}

# ── Hybrid retrieval weights ──────────────────────────────────────────────────
KEYWORD_WEIGHT  = 0.40   # weight for SAS-keyword TF-cosine score
SEMANTIC_WEIGHT = 0.60   # weight for Nomic embedding cosine score

# ── SAS keyword vocabulary (91 tokens) ───────────────────────────────────────
_SAS_KEYWORDS: list[str] = [
    # Data step
    "data", "set", "merge", "by", "if", "then", "else", "end", "do", "while",
    "until", "output", "retain", "keep", "drop", "rename", "length", "label",
    "format", "informat", "attrib", "array", "input", "put", "file", "infile",
    "datalines", "cards", "firstobs", "obs", "where", "delete", "return",
    "stop", "abort", "call", "link", "goto",
    # FIRST / LAST
    "first", "last",
    # Functions
    "lag", "sum", "mean", "min", "max", "count", "n", "nmiss", "substr",
    "scan", "trim", "strip", "upcase", "lowcase", "compress", "cat", "cats",
    "catx", "today", "date", "mdy", "year", "month", "day", "intck", "intnx",
    "input_fn", "put_fn", "abs", "round", "int", "log", "exp", "sqrt",
    # Procs
    "proc", "run", "quit",
    "sort", "print", "means", "freq", "univariate", "reg", "logistic",
    "glm", "mixed", "transpose", "export", "import", "sql", "report",
    "tabulate", "format_proc", "contents", "datasets", "copy", "append",
    "sgplot", "gplot", "chart",
    # SQL
    "select", "from", "join", "inner", "outer", "left", "right", "full",
    "group", "having", "order", "create", "insert", "update", "delete_sql",
    "where_sql",
    # Macro
    "macro", "mend", "let", "global", "local", "put_macro", "if_macro",
    "do_macro", "include",
    # Misc
    "libname", "filename", "options", "title", "footnote", "ods",
    "nodupkey", "noduprec", "descending",
]

# Pre-build index for fast lookup
_KW_INDEX = {kw: i for i, kw in enumerate(_SAS_KEYWORDS)}
_N_KW = len(_SAS_KEYWORDS)


def _get_db(db_path: str) -> lancedb.DBConnection:
    """Return a shared LanceDB connection (singleton per path)."""
    if db_path not in _db_connections:
        _db_connections[db_path] = lancedb.connect(db_path)
    return _db_connections[db_path]


# ── Keyword vectoriser ────────────────────────────────────────────────────────

def _keyword_vector(sas_code: str) -> list[float]:
    """Compute a TF-normalised keyword frequency vector for ``sas_code``.

    Returns a length-91 float list (L2-normalised).
    Strips comments and string literals before tokenising.
    """
    # Remove block comments and string literals
    code = re.sub(r"/\*.*?\*/", " ", sas_code, flags=re.DOTALL)
    code = re.sub(r"'[^']*'", " ", code)
    code = re.sub(r'"[^"]*"', " ", code)

    tokens = re.split(r"[^A-Za-z0-9_]", code.lower())
    counts = [0.0] * _N_KW
    total  = 0

    for tok in tokens:
        tok = tok.strip("_")
        if tok in _KW_INDEX:
            counts[_KW_INDEX[tok]] += 1.0
            total += 1

    if total == 0:
        return counts

    # TF normalisation
    counts = [c / total for c in counts]

    # L2 normalisation
    norm = sum(c * c for c in counts) ** 0.5
    if norm > 0:
        counts = [c / norm for c in counts]

    return counts


def _cosine(a: list[float], b: list[float]) -> float:
    """Dot product of two L2-normalised vectors (= cosine similarity)."""
    return sum(x * y for x, y in zip(a, b))


def _deduplicate_issues(examples: list[dict]) -> list[dict]:
    """Remove duplicate issue strings across KB examples.

    Uses exact match + simple token-overlap (Jaccard ≥ 0.85) to collapse
    near-identical lessons so the prompt doesn't repeat the same guidance.
    """
    seen_issues: set[str] = set()

    def _tokens(s: str) -> set[str]:
        return set(re.split(r"\W+", s.lower()))

    def _is_duplicate(issue: str) -> bool:
        issue_lower = issue.lower().strip()
        if issue_lower in seen_issues:
            return True
        toks = _tokens(issue)
        for seen in seen_issues:
            seen_toks = _tokens(seen)
            union = len(toks | seen_toks)
            if union == 0:
                continue
            jaccard = len(toks & seen_toks) / union
            if jaccard >= 0.85:
                return True
        return False

    result = []
    for ex in examples:
        deduped_issues = []
        for issue in ex.get("issues", []):
            if not _is_duplicate(issue):
                seen_issues.add(issue.lower().strip())
                deduped_issues.append(issue)
        ex = dict(ex)
        ex["issues"] = deduped_issues
        result.append(ex)

    return result


class KBQueryClient:
    """Query the sas_python_examples KB in LanceDB using hybrid retrieval."""

    TABLE_NAME = "sas_python_examples"
    MIN_RELEVANCE = 0.40   # lowered from 0.50 — keyword boost can lift lower-semantic items

    def __init__(self, db_path: str = "data/lancedb"):
        self.db = _get_db(db_path)

    def retrieve_examples(
        self,
        query_embedding: list[float],
        partition_type: str,
        failure_mode: Optional[str] = None,
        target_runtime: str = "python",
        k: int = 5,
        sas_code: str = "",
    ) -> list[dict]:
        """Retrieve k most relevant KB examples using hybrid scoring.

        Scoring:
          hybrid = KEYWORD_WEIGHT * keyword_cosine + SEMANTIC_WEIGHT * semantic_cosine

        Filters:
          - partition_type must match (exact)
          - failure_mode must match (if specified)
          - target_runtime must match
          - verified = True only
          - hybrid score >= MIN_RELEVANCE

        Post-processing:
          - Issue deduplication across all returned examples

        Args:
            query_embedding: Pre-computed Nomic 768-dim embedding of the query.
            partition_type:  SAS block type string.
            failure_mode:    Detected failure mode (optional).
            target_runtime:  "python" or "pyspark".
            k:               Number of candidates to retrieve (semantic pre-fetch = 3k).
            sas_code:        Raw SAS source code for keyword scoring.
        """
        if self.TABLE_NAME not in self.db.table_names():
            logger.warning("kb_table_missing", table=self.TABLE_NAME)
            return []

        table = self.db.open_table(self.TABLE_NAME)

        def _safe(val: str) -> str:
            if not _SAFE_VALUE.match(val):
                raise ValueError(f"Unsafe filter value: {val!r}")
            return val

        where_parts = [
            f"partition_type = '{_safe(partition_type)}'",
            f"target_runtime = '{_safe(target_runtime)}'",
            "verified = true",
        ]
        if failure_mode:
            where_parts.append(f"failure_mode = '{_safe(failure_mode)}'")
        where_clause = " AND ".join(where_parts)

        try:
            # Over-fetch for hybrid re-ranking (3k candidates, then keep top k)
            prefetch_k = min(k * 3, 30)
            results = (
                table.search(query_embedding)
                .where(where_clause)
                .limit(prefetch_k)
                .to_pandas()
            )

            if results.empty:
                return []

            if "_distance" in results.columns:
                results["semantic_score"] = 1.0 - results["_distance"]
            else:
                results["semantic_score"] = 0.5

            # ── Hybrid scoring ────────────────────────────────────────────────
            query_kv = _keyword_vector(sas_code) if sas_code else [0.0] * _N_KW

            hybrid_scores: list[float] = []
            for _, row in results.iterrows():
                kb_sas = row.get("sas_code", "") or ""
                kb_kv  = _keyword_vector(kb_sas) if kb_sas else [0.0] * _N_KW
                kw_sim = _cosine(query_kv, kb_kv) if sas_code else 0.0
                sem    = float(row["semantic_score"])
                hybrid = KEYWORD_WEIGHT * kw_sim + SEMANTIC_WEIGHT * sem
                hybrid_scores.append(hybrid)

            results["hybrid_score"] = hybrid_scores
            results = results[results["hybrid_score"] >= self.MIN_RELEVANCE]
            results = results.sort_values("hybrid_score", ascending=False).head(k)

            examples = []
            for _, row in results.iterrows():
                issues_raw  = row.get("issues_text", "") or ""
                issues_list = [i.strip() for i in issues_raw.split("|") if i.strip()]
                examples.append({
                    "example_id":     row["example_id"],
                    "sas_code":       row["sas_code"],
                    "python_code":    row["python_code"],
                    "similarity":     row.get("hybrid_score", 0),
                    "semantic_score": row.get("semantic_score", 0),
                    "failure_mode":   row.get("failure_mode", ""),
                    "category":       row.get("category", ""),
                    "issues":         issues_list,
                })

            # Deduplicate issues across examples
            examples = _deduplicate_issues(examples)

            logger.info(
                "kb_hybrid_retrieved",
                partition_type=partition_type,
                failure_mode=failure_mode,
                k=k,
                returned=len(examples),
                keyword_weight=KEYWORD_WEIGHT,
                semantic_weight=SEMANTIC_WEIGHT,
            )
            return examples

        except Exception as e:
            logger.warning("kb_query_failed", error=str(e))
            return []
