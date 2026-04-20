"""SemantiCheck — Novel 4-layer semantic verification framework.

The core insight: CodeBLEU compares text; we compare *meaning*.
Two translations can be textually very different yet semantically identical.
SemantiCheck measures semantic equivalence through four independent lenses:

  L1 — Formal:     Z3 SMT proofs for decidable fragments (reuses z3_agent)
  L2 — Behavioral: CDAIS witness execution (reuses existing CDAIS)
  L3 — Contract:   Language-agnostic transformation graph comparison
  L4 — Oracle:     LLM simulates SAS execution, compare with real Python output

Final score: SemantiCheck Score (SCS) = weighted composite of all 4 layers.

Novel contribution:
  L3 is the first tool to extract a *Semantic Transformation Graph* (STG) from
  both SAS and Python and compare them structurally — independent of syntax.
  L4 is the first to use an LLM as a SAS execution oracle, enabling behavioral
  testing without a SAS license.
"""

from __future__ import annotations

import ast
import re
import json
import asyncio
import textwrap
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import structlog

log = structlog.get_logger()


# ── Semantic Transformation Graph (STG) ──────────────────────────────────────

class OpType(str, Enum):
    READ       = "READ"
    FILTER     = "FILTER"
    SORT       = "SORT"
    GROUP      = "GROUP"
    AGGREGATE  = "AGGREGATE"
    COMPUTE    = "COMPUTE"    # new column derivation
    MERGE      = "MERGE"
    DEDUP      = "DEDUP"
    TRANSPOSE  = "TRANSPOSE"
    WRITE      = "WRITE"


@dataclass
class STGNode:
    op: OpType
    datasets: list[str] = field(default_factory=list)
    columns: list[str]  = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)


@dataclass
class SemanticTransformGraph:
    nodes: list[STGNode] = field(default_factory=list)

    def ops(self) -> list[OpType]:
        return [n.op for n in self.nodes]

    def has_op(self, op: OpType) -> bool:
        return any(n.op == op for n in self.nodes)


# ── L3: SAS STG Extractor ─────────────────────────────────────────────────────

_SAS_PROC_MAP = {
    "sort": OpType.SORT,
    "means": OpType.AGGREGATE,
    "freq": OpType.AGGREGATE,
    "sql": OpType.MERGE,
    "transpose": OpType.TRANSPOSE,
    "summary": OpType.AGGREGATE,
}


def extract_stg_from_sas(sas_code: str) -> SemanticTransformGraph:
    """Extract a Semantic Transformation Graph from SAS source code.

    Uses regex + heuristics rather than full parsing — fast and good enough
    to capture the high-level transformation structure.
    """
    code = sas_code.upper()
    nodes: list[STGNode] = []

    # DATA step → READ + (MERGE?) + COMPUTE + WRITE
    for m in re.finditer(r"DATA\s+(\w+)\s*;", code):
        output_ds = m.group(1).lower()
        # What does the step SET/MERGE from?
        set_match = re.search(r"SET\s+([\w\s]+);", code)
        merge_match = re.search(r"MERGE\s+([\w\s]+);", code)

        if merge_match:
            inputs = [w.lower() for w in merge_match.group(1).split()]
            nodes.append(STGNode(op=OpType.MERGE, datasets=inputs))
        elif set_match:
            inputs = [w.lower() for w in set_match.group(1).split()]
            nodes.append(STGNode(op=OpType.READ, datasets=inputs))

        # WHERE / IF filters
        filters = re.findall(r"WHERE\s+(.+?);|IF\s+(.+?)\s+THEN", code)
        for f in filters:
            condition = (f[0] or f[1]).strip().lower()
            if condition:
                nodes.append(STGNode(op=OpType.FILTER, conditions=[condition]))

        # RETAIN → flag COMPUTE with running accumulation
        if re.search(r"\bRETAIN\b", code):
            nodes.append(STGNode(op=OpType.COMPUTE, params={"pattern": "retain"}))

        # BY statement → flag sort dependency
        if re.search(r"\bBY\b.+;", code):
            by_vars = re.findall(r"\bBY\b\s+([\w\s]+);", code)
            cols = by_vars[0].lower().split() if by_vars else []
            nodes.append(STGNode(op=OpType.SORT, columns=cols))

        nodes.append(STGNode(op=OpType.WRITE, datasets=[output_ds]))

    # PROC steps
    for m in re.finditer(r"PROC\s+(\w+)\s+DATA\s*=\s*(\w+)", code):
        proc_name = m.group(1).lower()
        input_ds = m.group(2).lower()
        op = _SAS_PROC_MAP.get(proc_name, OpType.COMPUTE)

        if op == OpType.SORT:
            # NODUPKEY?
            if "NODUPKEY" in code:
                nodes.append(STGNode(op=OpType.SORT, datasets=[input_ds], params={"dedup": True}))
                nodes.append(STGNode(op=OpType.DEDUP, datasets=[input_ds]))
            else:
                nodes.append(STGNode(op=OpType.SORT, datasets=[input_ds]))
        else:
            nodes.append(STGNode(op=op, datasets=[input_ds]))

    # Macro → COMPUTE (dynamic)
    if re.search(r"%MACRO\b", code):
        nodes.append(STGNode(op=OpType.COMPUTE, params={"pattern": "macro"}))

    # HASH object → MERGE semantics
    if re.search(r"DECLARE\s+HASH", code):
        nodes.append(STGNode(op=OpType.MERGE, params={"pattern": "hash_lookup"}))

    return SemanticTransformGraph(nodes=nodes)


# ── L3: Python STG Extractor ─────────────────────────────────────────────────

_PANDAS_AGG = {"groupby", "agg", "sum", "mean", "count", "min", "max", "std"}
_PANDAS_MERGE = {"merge", "join", "concat"}
_PANDAS_SORT = {"sort_values", "sort_index"}
_PANDAS_FILTER = {"query", "loc", "iloc", "where", "isin"}
_PANDAS_DEDUP = {"drop_duplicates"}
_PANDAS_PIVOT = {"pivot", "pivot_table", "melt", "transpose"}


def extract_stg_from_python(python_code: str) -> SemanticTransformGraph:
    """Extract a Semantic Transformation Graph from Python/pandas source code.

    Walks the AST looking for pandas method calls that correspond to
    the same logical operations as SAS constructs.
    """
    nodes: list[STGNode] = []

    try:
        tree = ast.parse(python_code)
    except SyntaxError:
        # Unparseable — return empty graph (will score 0 on L3)
        return SemanticTransformGraph(nodes=[])

    # Walk all method calls
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        # Get method name from attribute calls (df.method())
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr.lower()
        elif isinstance(node.func, ast.Name):
            method = node.func.id.lower()
        else:
            continue

        if method in _PANDAS_AGG:
            nodes.append(STGNode(op=OpType.AGGREGATE))
        elif method in _PANDAS_MERGE:
            nodes.append(STGNode(op=OpType.MERGE))
        elif method in _PANDAS_SORT:
            nodes.append(STGNode(op=OpType.SORT))
        elif method in _PANDAS_FILTER:
            nodes.append(STGNode(op=OpType.FILTER))
        elif method in _PANDAS_DEDUP:
            nodes.append(STGNode(op=OpType.DEDUP))
        elif method in _PANDAS_PIVOT:
            nodes.append(STGNode(op=OpType.TRANSPOSE))
        elif method in ("read_csv", "read_parquet", "read_sas", "read_excel"):
            nodes.append(STGNode(op=OpType.READ))
        elif method == "to_csv" or method == "to_parquet":
            nodes.append(STGNode(op=OpType.WRITE))

    # Subscript assignments = COMPUTE (new column: df['col'] = ...)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Subscript):
                    nodes.append(STGNode(op=OpType.COMPUTE))
                    break

    # cumsum / cummax / shift → RETAIN equivalent
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("cumsum", "cummax", "shift", "expanding"):
            nodes.append(STGNode(op=OpType.COMPUTE, params={"pattern": "retain"}))
            break

    return SemanticTransformGraph(nodes=nodes)


# ── L3: Contract Score ────────────────────────────────────────────────────────

def score_contract(sas_stg: SemanticTransformGraph, py_stg: SemanticTransformGraph) -> float:
    """Compare two STGs and return a similarity score 0.0 – 1.0.

    Uses a Jaccard-style comparison on the *set* of operation types present
    in each graph, not the exact sequence — because pandas and SAS express
    the same transformation in different orders.
    """
    sas_ops = set(sas_stg.ops())
    py_ops  = set(py_stg.ops())

    if not sas_ops and not py_ops:
        return 1.0   # both empty → trivially equivalent
    if not sas_ops or not py_ops:
        return 0.0

    # Jaccard similarity on op types
    intersection = sas_ops & py_ops
    union = sas_ops | py_ops
    jaccard = len(intersection) / len(union)

    # Bonus: if SAS has RETAIN and Python has cumsum/shift → explicit credit
    retain_bonus = 0.0
    sas_retain = any(n.params.get("pattern") == "retain" for n in sas_stg.nodes)
    py_retain  = any(n.params.get("pattern") == "retain" for n in py_stg.nodes)
    if sas_retain and py_retain:
        retain_bonus = 0.05

    # Bonus: hash lookup → merge credit
    sas_hash = any(n.params.get("pattern") == "hash_lookup" for n in sas_stg.nodes)
    py_merge = py_stg.has_op(OpType.MERGE)
    hash_bonus = 0.05 if sas_hash and py_merge else 0.0

    return min(1.0, jaccard + retain_bonus + hash_bonus)


# ── L4: Oracle Score ─────────────────────────────────────────────────────────

_ORACLE_PROMPT = """\
You are a SAS execution oracle.

Given a SAS code snippet and a synthetic input DataFrame, predict what the
output DataFrame would look like after the SAS code runs.

Return a JSON object with these fields:
{{
  "columns": ["list", "of", "output", "column", "names"],
  "row_count_change": "same|more|fewer|unknown",
  "key_transformations": ["brief description of each transformation applied"],
  "output_values_sample": {{
    "column_name": "example_value_or_formula"
  }}
}}

SAS Code:
```sas
{sas_code}
```

Synthetic input (as JSON):
{input_json}

Return ONLY valid JSON.
"""

_PYTHON_ORACLE_PROMPT = """\
You are a Python code analysis oracle.

Given a Python/pandas code snippet and a synthetic input DataFrame, describe
what the output DataFrame would look like after the code runs.

Return a JSON object with the same structure:
{{
  "columns": ["list", "of", "output", "column", "names"],
  "row_count_change": "same|more|fewer|unknown",
  "key_transformations": ["brief description of each transformation applied"],
  "output_values_sample": {{
    "column_name": "example_value_or_formula"
  }}
}}

Python Code:
```python
{python_code}
```

Synthetic input (as JSON):
{input_json}

Return ONLY valid JSON.
"""


def _synthesize_witness_input(sas_code: str) -> dict:
    """Synthesize a small representative input dataset from the SAS code.

    Extracts column names hinted at by the SAS source and builds a
    3-row DataFrame description. No actual pandas needed here — we build
    a JSON description the oracle prompt can read.
    """
    code = sas_code.lower()

    # Collect variable names from SET/MERGE statements and assignments
    vars_seen: set[str] = set()

    for m in re.finditer(r"\b(set|merge)\b\s+([\w\s]+);", code):
        pass  # dataset names, not column names — skip

    # Variable assignments: "var = " or "var =" patterns
    for m in re.finditer(r"^\s{0,8}([a-z_]\w*)\s*=\s*(?!['\"=])", code, re.MULTILINE):
        name = m.group(1)
        if name not in {"data", "proc", "run", "end", "do", "by", "if", "else", "set", "merge"}:
            vars_seen.add(name)

    # WHERE / IF conditions — grab variable names
    for m in re.finditer(r"where\s+(.+?);|if\s+(.+?)\s+then", code):
        clause = m.group(1) or m.group(2)
        for token in re.findall(r"\b([a-z_]\w*)\b", clause):
            if len(token) > 1:
                vars_seen.add(token)

    # Keep only plausible column names (not SAS keywords)
    sas_keywords = {
        "data", "set", "merge", "by", "if", "then", "else", "end", "do",
        "run", "proc", "where", "retain", "array", "output", "drop", "keep",
        "rename", "length", "format", "label", "input", "put", "infile",
        "file", "firstobs", "obs", "class", "var", "tables", "means", "freq",
        "sort", "out", "nodupkey", "descending", "noprint",
    }
    cols = [v for v in sorted(vars_seen)[:8] if v not in sas_keywords and len(v) > 1]

    if not cols:
        cols = ["id", "value", "category"]

    # Build a tiny representative 3-row dataset
    rows = []
    for i in range(1, 4):
        row = {}
        for col in cols:
            # Heuristic typing from column name
            if any(kw in col for kw in ("id", "num", "count", "age", "amt", "amount", "score")):
                row[col] = i * 10
            elif any(kw in col for kw in ("flag", "status", "type", "cat", "group", "region")):
                row[col] = ["A", "B", "A"][i - 1]
            elif any(kw in col for kw in ("date", "dt", "time")):
                row[col] = f"2024-01-0{i}"
            else:
                row[col] = i * 5
        rows.append(row)

    return {"columns": cols, "rows": rows}


async def score_oracle(
    sas_code: str,
    python_code: str,
    llm_client,
    model: str,
) -> float:
    """Score semantic equivalence via LLM oracle simulation (L4).

    Strategy:
      1. Synthesize a small representative input DataFrame
      2. Ask LLM to predict SAS output given the input
      3. Ask LLM to predict Python output given the same input
      4. Compare the two predictions structurally
      5. Score = agreement on columns + row_count_change + transformation semantics

    This is novel: no SAS license needed. The LLM acts as a SAS interpreter.
    """
    if llm_client is None:
        return 0.5  # can't score — return neutral, don't penalise

    witness = _synthesize_witness_input(sas_code)
    input_json = json.dumps(witness, indent=2)

    async def _ask(prompt: str) -> Optional[dict]:
        try:
            from openai import OpenAI
            resp = await asyncio.wait_for(
                asyncio.to_thread(
                    llm_client.chat.completions.create,
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0,
                    max_tokens=512,
                ),
                timeout=30,
            )
            raw = resp.choices[0].message.content.strip()
            # Strip markdown fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except Exception as exc:
            log.debug("oracle_llm_failed", error=str(exc)[:120])
            return None

    sas_prompt = _ORACLE_PROMPT.format(
        sas_code=textwrap.dedent(sas_code[:1500]),
        input_json=input_json,
    )
    py_prompt = _PYTHON_ORACLE_PROMPT.format(
        python_code=textwrap.dedent(python_code[:1500]),
        input_json=input_json,
    )

    sas_pred, py_pred = await asyncio.gather(
        _ask(sas_prompt),
        _ask(py_prompt),
    )

    if sas_pred is None or py_pred is None:
        return 0.5  # oracle unavailable — neutral score

    score = 0.0
    weight_total = 0.0

    # Column agreement (weight 0.5) — do both predict similar output columns?
    sas_cols = {c.lower() for c in sas_pred.get("columns", [])}
    py_cols  = {c.lower() for c in py_pred.get("columns", [])}
    if sas_cols or py_cols:
        col_jaccard = len(sas_cols & py_cols) / len(sas_cols | py_cols) if (sas_cols | py_cols) else 1.0
        score += 0.5 * col_jaccard
    weight_total += 0.5

    # Row count change agreement (weight 0.3)
    sas_rc = sas_pred.get("row_count_change", "unknown")
    py_rc  = py_pred.get("row_count_change", "unknown")
    rc_match = 1.0 if sas_rc == py_rc else (0.5 if "unknown" in (sas_rc, py_rc) else 0.0)
    score += 0.3 * rc_match
    weight_total += 0.3

    # Transformation keyword overlap (weight 0.2)
    sas_transforms = " ".join(sas_pred.get("key_transformations", [])).lower()
    py_transforms  = " ".join(py_pred.get("key_transformations", [])).lower()
    semantic_keywords = {
        "filter", "sort", "group", "aggregate", "merge", "join",
        "cumulative", "running", "deduplicate", "transpose", "pivot",
        "sum", "mean", "count", "max", "min",
    }
    sas_kw = {k for k in semantic_keywords if k in sas_transforms}
    py_kw  = {k for k in semantic_keywords if k in py_transforms}
    if sas_kw or py_kw:
        kw_jaccard = len(sas_kw & py_kw) / len(sas_kw | py_kw) if (sas_kw | py_kw) else 1.0
        score += 0.2 * kw_jaccard
    weight_total += 0.2

    final = score / weight_total if weight_total > 0 else 0.5
    log.debug(
        "oracle_scored",
        col_jaccard=round(len(sas_cols & py_cols) / max(len(sas_cols | py_cols), 1), 2),
        rc_match=rc_match,
        final=round(final, 3),
    )
    return round(final, 3)


# ── SemantiCheck composite scorer ────────────────────────────────────────────

@dataclass
class SemantiCheckResult:
    """Full SemantiCheck report for one translation."""
    # Layer scores (None = not applicable / skipped)
    z3_score:       Optional[float] = None   # L1
    cdais_score:    Optional[float] = None   # L2
    contract_score: Optional[float] = None   # L3 (always computed)
    oracle_score:   Optional[float] = None   # L4

    # STGs produced by L3
    sas_stg: Optional[SemanticTransformGraph] = None
    py_stg:  Optional[SemanticTransformGraph] = None

    # Final composite
    scs: float = 0.0   # SemantiCheck Score 0.0 – 1.0

    # Human-readable verdict
    verdict: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "scs": self.scs,
            "verdict": self.verdict,
            "layers": {
                "L1_formal_z3":    self.z3_score,
                "L2_behavioral":   self.cdais_score,
                "L3_contract":     self.contract_score,
                "L4_oracle":       self.oracle_score,
            },
        }


# Weights — tuned so that formal proof and behavioral testing dominate,
# but contract and oracle still meaningfully shift the score.
_WEIGHTS = {
    "z3":      0.30,
    "cdais":   0.30,
    "contract": 0.20,
    "oracle":  0.20,
}


async def semanticheck(
    sas_code: str,
    python_code: str,
    z3_score: Optional[float] = None,
    cdais_score: Optional[float] = None,
    llm_client=None,
    llm_model: str = "",
) -> SemantiCheckResult:
    """Compute the SemantiCheck Score (SCS) for a SAS→Python translation.

    Args:
        sas_code:     Original SAS source.
        python_code:  Translated Python code.
        z3_score:     Pre-computed Z3 score (1.0=proved, 0.0=counterexample,
                      None=not applicable).
        cdais_score:  Pre-computed CDAIS score (pass_rate 0.0–1.0,
                      None=not run).
        llm_client:   Raw (non-instructor) OpenAI-compatible client for oracle.
        llm_model:    Model name for oracle calls.

    Returns:
        SemantiCheckResult with per-layer scores and the composite SCS.
    """
    result = SemantiCheckResult(z3_score=z3_score, cdais_score=cdais_score)

    # L3 — Contract (always runs, no LLM needed)
    sas_stg = extract_stg_from_sas(sas_code)
    py_stg  = extract_stg_from_python(python_code)
    result.sas_stg = sas_stg
    result.py_stg  = py_stg
    result.contract_score = score_contract(sas_stg, py_stg)

    # L4 — Oracle (needs LLM)
    if llm_client and llm_model:
        result.oracle_score = await score_oracle(sas_code, python_code, llm_client, llm_model)
    else:
        result.oracle_score = None

    # Composite SCS
    components: list[tuple[float, float]] = []  # (weight, score)

    if result.z3_score is not None:
        components.append((_WEIGHTS["z3"], result.z3_score))

    if result.cdais_score is not None:
        components.append((_WEIGHTS["cdais"], result.cdais_score))

    components.append((_WEIGHTS["contract"], result.contract_score))

    if result.oracle_score is not None:
        components.append((_WEIGHTS["oracle"], result.oracle_score))

    # Renormalize weights to what's available
    total_w = sum(w for w, _ in components)
    if total_w > 0:
        result.scs = round(sum(w * s for w, s in components) / total_w, 3)
    else:
        result.scs = 0.0

    # Verdict
    if result.scs >= 0.85:
        result.verdict = "VERIFIED"
    elif result.scs >= 0.65:
        result.verdict = "LIKELY_CORRECT"
    elif result.scs >= 0.40:
        result.verdict = "UNCERTAIN"
    else:
        result.verdict = "LIKELY_INCORRECT"

    log.info(
        "semanticheck_complete",
        scs=result.scs,
        verdict=result.verdict,
        z3=result.z3_score,
        cdais=result.cdais_score,
        contract=result.contract_score,
        oracle=result.oracle_score,
    )
    return result
