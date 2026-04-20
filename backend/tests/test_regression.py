"""Regression test suite — end-to-end gold standard translation.

Loads each .sas file from knowledge_base/gold_standard/, runs the
translation pipeline (syntax validation only — no real LLM calls needed
for deterministic patterns, full LLM for the rest), and checks:

  1. Syntax validity of the translated Python code.
  2. Deterministic shortcut fires for PROC SORT / IMPORT / EXPORT / DATALINES.
  3. No internal-table reload violations (lineage guard).
  4. No `def main()` or unnecessary wrapper functions.

Parametrised with pytest so each gold standard file is a separate test case.

Run with::

    cd backend
    python -m pytest tests/test_regression.py -v --tb=short

To run only the deterministic-pattern cases (fast, no LLM)::

    python -m pytest tests/test_regression.py -v -k "deterministic"
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest

# Ensure backend is on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from partition.translation.deterministic_translator import try_deterministic
from partition.translation.lineage_guard import check_lineage, build_internal_table_set
from partition.translation.error_classifier import classify_error

GOLD_DIR = _ROOT / "knowledge_base" / "gold_standard"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_pairs() -> list[tuple[str, str, dict]]:
    """Return list of (sas_filename, sas_code, gold_meta) tuples."""
    pairs = []
    for sas_path in sorted(GOLD_DIR.glob("*.sas")):
        sas_code = sas_path.read_text(encoding="utf-8", errors="replace")
        gold_path = sas_path.with_suffix(".gold.json")
        gold_meta = json.loads(gold_path.read_text()) if gold_path.exists() else {}
        pairs.append((sas_path.name, sas_code, gold_meta))
    return pairs


_PAIRS = _load_pairs()


def _is_syntax_valid(code: str) -> tuple[bool, str]:
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, str(e)


def _has_def_main(code: str) -> bool:
    """Check for illegal `def main()` / `def run()` / `def process()` wrappers."""
    return bool(re.search(r"^\s*def\s+(main|run|process|execute)\s*\(", code, re.MULTILINE))


def _has_unnecessary_def(code: str) -> bool:
    """Flag any `def` that is not translating a macro (heuristic)."""
    # Any top-level def is suspicious unless it looks like a macro translation
    for m in re.finditer(r"^\s*def\s+(\w+)\s*\(", code, re.MULTILINE):
        fn_name = m.group(1)
        # Acceptable: named helper fns from %MACRO, utility fns
        # Flag: main/run/process wrappers
        if fn_name.lower() in ("main", "run", "process", "execute", "translate"):
            return True
    return False


# ── Deterministic-pattern tests ───────────────────────────────────────────────

DETERMINISTIC_PATTERNS = [
    "proc sort", "proc import", "proc export",
    "datalines", "cards", "proc print",
]


def _is_deterministic_candidate(sas_code: str) -> bool:
    code_lower = sas_code.lower()
    return any(p in code_lower for p in DETERMINISTIC_PATTERNS)


@pytest.mark.parametrize("name,sas_code,gold_meta", _PAIRS, ids=[p[0] for p in _PAIRS])
def test_syntax_validity_after_deterministic(name: str, sas_code: str, gold_meta: dict):
    """Deterministic translations must produce syntactically valid Python."""
    result = try_deterministic(sas_code)
    if result is None:
        pytest.skip(f"{name}: no deterministic rule matched")

    valid, err = _is_syntax_valid(result.code)
    assert valid, f"{name} [{result.reason}]: SyntaxError: {err}\n---\n{result.code}"


@pytest.mark.parametrize("name,sas_code,gold_meta", _PAIRS, ids=[p[0] for p in _PAIRS])
def test_deterministic_fires_for_known_patterns(name: str, sas_code: str, gold_meta: dict):
    """Deterministic translator must fire for PROC SORT / IMPORT / EXPORT / PRINT / DATALINES."""
    if not _is_deterministic_candidate(sas_code):
        pytest.skip(f"{name}: not a deterministic candidate")

    result = try_deterministic(sas_code)
    # For simple (single-proc) files, we expect a hit
    gold_tier = gold_meta.get("tier", "")
    if gold_tier == "simple":
        assert result is not None, (
            f"{name}: expected deterministic translation for simple tier, got None"
        )


# ── Lineage guard tests ───────────────────────────────────────────────────────

@pytest.mark.parametrize("name,sas_code,gold_meta", _PAIRS, ids=[p[0] for p in _PAIRS])
def test_no_lineage_violations_in_deterministic(name: str, sas_code: str, gold_meta: dict):
    """Deterministic translations must not reload internal tables from disk."""
    result = try_deterministic(sas_code)
    if result is None:
        pytest.skip(f"{name}: no deterministic rule matched")

    internal = build_internal_table_set(sas_code)
    report = check_lineage(result.code, internal_table_names=internal)
    assert report.ok, (
        f"{name}: lineage violation in deterministic code:\n"
        + report.to_prompt_block()
    )


# ── No-def tests ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,sas_code,gold_meta", _PAIRS, ids=[p[0] for p in _PAIRS])
def test_no_def_main_in_deterministic(name: str, sas_code: str, gold_meta: dict):
    """Deterministic translations must never wrap output in def main()."""
    result = try_deterministic(sas_code)
    if result is None:
        pytest.skip(f"{name}: no deterministic rule matched")

    assert not _has_def_main(result.code), (
        f"{name}: deterministic code contains illegal def main() wrapper"
    )


# ── Error classifier unit tests ───────────────────────────────────────────────

class TestErrorClassifier:
    def test_syntax_error(self):
        from partition.translation.error_classifier import SYNTAX
        r = classify_error("SyntaxError: unexpected EOF", "", "def foo(")
        assert r.primary_category == SYNTAX

    def test_key_error_col(self):
        from partition.translation.error_classifier import COL_MISSING
        r = classify_error("KeyError: 'amount'", "", "df['amount'] + 1")
        assert r.primary_category == COL_MISSING
        assert "amount" in r.affected_columns

    def test_type_error_dtype(self):
        from partition.translation.error_classifier import DTYPE_MISMATCH, TYPE_ERROR
        r = classify_error("TypeError: can only concatenate str (not 'int') to str", "")
        assert r.primary_category in (DTYPE_MISMATCH, TYPE_ERROR)

    def test_empty_dataframe(self):
        from partition.translation.error_classifier import EMPTY_SUSPICIOUS
        r = classify_error("empty dataframe: length 0", "")
        assert r.primary_category == EMPTY_SUSPICIOUS

    def test_merge_contract(self):
        from partition.translation.error_classifier import MERGE_CONTRACT
        r = classify_error("merge semantics mismatch in_left in_right", "")
        assert r.primary_category == MERGE_CONTRACT

    def test_fallthrough(self):
        from partition.translation.error_classifier import RUNTIME_GENERAL
        r = classify_error("some unknown runtime error", "")
        assert r.primary_category == RUNTIME_GENERAL


# ── Deterministic translator unit tests ──────────────────────────────────────

class TestDeterministicTranslator:
    def test_proc_sort_basic(self):
        sas = "proc sort data=myds; by name; run;"
        r = try_deterministic(sas)
        assert r is not None
        assert "sort_values" in r.code
        assert "['name']" in r.code

    def test_proc_sort_nodupkey(self):
        sas = "proc sort data=myds nodupkey; by id; run;"
        r = try_deterministic(sas)
        assert r is not None
        assert "drop_duplicates" in r.code

    def test_proc_sort_descending(self):
        sas = "proc sort data=ds; by descending score; run;"
        r = try_deterministic(sas)
        assert r is not None
        assert "False" in r.code   # ascending=False

    def test_proc_import_csv(self):
        sas = "proc import datafile='data.csv' out=raw dbms=csv replace; run;"
        r = try_deterministic(sas)
        assert r is not None
        assert "read_csv" in r.code
        assert "raw" in r.code

    def test_proc_export_csv(self):
        sas = "proc export data=final outfile='output.csv' dbms=csv replace; run;"
        r = try_deterministic(sas)
        assert r is not None
        assert "to_csv" in r.code

    def test_proc_print(self):
        sas = "proc print data=myds(obs=10); run;"
        r = try_deterministic(sas)
        assert r is not None
        assert "head(10)" in r.code

    def test_simple_data_copy(self):
        sas = "data out; set inp; run;"
        r = try_deterministic(sas)
        assert r is not None
        assert "out = inp.copy()" in r.code

    def test_no_match_for_complex(self):
        sas = "data out; set inp; if flag=1 then do; x=x+1; end; run;"
        r = try_deterministic(sas)
        assert r is None, "complex DATA step should not match deterministic rules"


# ── Lineage guard unit tests ──────────────────────────────────────────────────

class TestLineageGuard:
    def test_clean_code(self):
        code = "result = customers.merge(orders, on='id')"
        report = check_lineage(code, {"customers", "orders"})
        assert report.ok

    def test_detects_reload(self):
        code = "customers = pd.read_csv('customers.csv')"
        report = check_lineage(code, {"customers"})
        assert not report.ok
        assert "customers" in report.violations[0].table_name

    def test_allows_external_file(self):
        code = "raw = pd.read_csv('/data/external/source.csv')"
        report = check_lineage(code, {"customers"})
        assert report.ok, "External path should not be flagged as internal reload"

    def test_build_internal_set(self):
        sas = "data work.output; set input; run; proc sort data=result; by id; run;"
        names = build_internal_table_set(sas)
        assert "output" in names
        assert "result" in names
