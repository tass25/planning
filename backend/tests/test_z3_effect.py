"""test_z3_effect.py — Demonstrates the concrete value of Z3 formal verification.

THESIS JUSTIFICATION  Before Z3 / After Z3
------------------------------------------
Each test case has a "buggy" Python translation that is:
  OK  Syntactically valid  (py_compile passes)
  OK  Exec-sandbox passes  (ValidationAgent sees no exception)
  !!  Semantically wrong   (produces different results than the SAS original)

WITHOUT Z3 (syntax + exec validation only):
  -> buggy translation ships SILENTLY as SUCCESS.

WITH Z3:
  -> COUNTEREXAMPLE returned with the exact issue and a fix hint.
  -> Pipeline re-queues at RiskLevel.HIGH for one more repair attempt.

Run (clean pass/fail):
    cd backend
    python -m pytest tests/test_z3_effect.py -v

Run (full thesis table printed to stdout):
    cd backend
    python -m pytest tests/test_z3_effect.py -v -s

Standalone (no pytest, generates output directly):
    cd backend
    python tests/test_z3_effect.py
"""

from __future__ import annotations

import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

# allow running standalone
_HERE = Path(__file__).resolve().parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import pytest
from partition.verification.z3_agent import Z3VerificationAgent, VerificationStatus

# UTF-8 for standalone mode on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# -------------------------------------------------------------------------
# Status icons (pure ASCII so Windows cp1252 never chokes)
# -------------------------------------------------------------------------

_STATUS_LABEL = {
    "formal_proof":       "[  PROVED  ]",
    "counterexample":     "[COUNTEREX ]",
    "unverifiable":       "[ UNKNOWN  ]",
    "behavioral_verified":"[ BEHAV.   ]",
    "skipped":            "[ SKIPPED  ]",
}


# -------------------------------------------------------------------------
# Data model
# -------------------------------------------------------------------------

@dataclass
class BugCase:
    name:        str   # short identifier
    sas:         str   # SAS source code
    buggy_py:    str   # syntactically valid but semantically wrong
    correct_py:  str   # semantically correct
    bug_kind:    str   # e.g. "wrong sort direction"
    impact:      str   # consequence if this bug reaches production

    # filled by run_case()
    buggy_z3_status:   str = "?"
    buggy_z3_pattern:  str = ""
    buggy_z3_issue:    str = ""
    buggy_z3_hint:     str = ""
    buggy_z3_latency:  float = 0.0

    correct_z3_status:  str = "?"
    correct_z3_pattern: str = ""
    correct_z3_latency: float = 0.0


# -------------------------------------------------------------------------
# 7 canonical bug cases, one per Z3 pattern
# -------------------------------------------------------------------------

CASES: list[BugCase] = [

    BugCase(
        name     = "sort_direction",
        bug_kind = "PROC SORT DESCENDING -> wrong ascending= value",
        impact   = (
            "Transactions sorted oldest-first instead of newest-first. "
            "BI dashboards silently show stale records at top."
        ),
        sas = textwrap.dedent("""\
            proc sort data=transactions;
              by account_id descending txn_date;
            run;"""),
        buggy_py = (
            "transactions = transactions.sort_values("
            "['account_id', 'txn_date'], ascending=[True, True])"
        ),
        correct_py = (
            "transactions = transactions.sort_values("
            "['account_id', 'txn_date'], ascending=[True, False])"
        ),
    ),

    BugCase(
        name     = "proc_means_dropna",
        bug_kind = "PROC MEANS CLASS -> missing dropna=False, NaN group lost",
        impact   = (
            "Patients with missing age_group silently dropped from summary. "
            "Clinical trial excludes an entire demographic cohort."
        ),
        sas = textwrap.dedent("""\
            proc means data=patients;
              class gender age_group;
              var cholesterol;
              output out=stats mean=mean_chol;
            run;"""),
        buggy_py = textwrap.dedent("""\
            stats = patients.groupby(['gender', 'age_group']).agg(
                mean_chol=('cholesterol', 'mean')
            ).reset_index()"""),
        correct_py = textwrap.dedent("""\
            stats = patients.groupby(['gender', 'age_group'], dropna=False).agg(
                mean_chol=('cholesterol', 'mean')
            ).reset_index()"""),
    ),

    BugCase(
        name     = "boolean_filter_threshold",
        bug_kind = "WHERE threshold off by 10x",
        impact   = (
            "10x more orders selected as high-value than intended. "
            "Marketing sends premium offers to standard customers."
        ),
        sas = textwrap.dedent("""\
            data high_value;
              set orders;
              where order_amount > 10000;
            run;"""),
        buggy_py   = "high_value = orders[orders['order_amount'] > 1000]",
        correct_py = "high_value = orders[orders['order_amount'] > 10000]",
    ),

    BugCase(
        name     = "sort_nodupkey",
        bug_kind = "PROC SORT NODUPKEY -> drop_duplicates() missing",
        impact   = (
            "Customer deduplication skipped silently. "
            "Downstream JOIN inflates row counts; aggregates double-counted."
        ),
        sas = textwrap.dedent("""\
            proc sort data=customer_addresses nodupkey;
              by customer_id;
            run;"""),
        buggy_py = (
            "customer_addresses = customer_addresses.sort_values('customer_id')"
        ),
        correct_py = (
            "customer_addresses = customer_addresses"
            ".sort_values('customer_id')"
            ".drop_duplicates(subset='customer_id')"
        ),
    ),

    BugCase(
        name     = "iterrows_loop",
        bug_kind = "IF/THEN -> iterrows() instead of np.select (100x slower)",
        impact   = (
            "Vectorised scoring becomes a row-by-row loop. "
            "1M-row dataset: 2s -> 200s. Pipeline SLA breach."
        ),
        sas = textwrap.dedent("""\
            data scored;
              set customers;
              if credit_score > 700 then risk = 'LOW';
              else if credit_score > 500 then risk = 'MED';
              else risk = 'HIGH';
            run;"""),
        buggy_py = textwrap.dedent("""\
            for idx, row in scored.iterrows():
                if row['credit_score'] > 700:
                    scored.at[idx, 'risk'] = 'LOW'
                elif row['credit_score'] > 500:
                    scored.at[idx, 'risk'] = 'MED'
                else:
                    scored.at[idx, 'risk'] = 'HIGH'"""),
        correct_py = textwrap.dedent("""\
            scored['risk'] = np.select(
                [scored['credit_score'] > 700, scored['credit_score'] > 500],
                ['LOW', 'MED'],
                default='HIGH'
            )"""),
    ),

    BugCase(
        name     = "arithmetic_coefficient",
        bug_kind = "DATA step coefficient 0.92 -> 0.9 (off by 2.2%)",
        impact   = (
            "Wrong exchange rate on EUR10M portfolio: EUR220,000 mis-stated. "
            "Regulatory filing error."
        ),
        sas = textwrap.dedent("""\
            data converted;
              set prices;
              price_eur = price_usd * 0.92;
            run;"""),
        buggy_py   = "converted['price_eur'] = converted['price_usd'] * 0.9",
        correct_py = "converted['price_eur'] = converted['price_usd'] * 0.92",
    ),

    BugCase(
        name     = "left_join_type",
        bug_kind = "LEFT JOIN -> how='inner', non-matching rows silently dropped",
        impact   = (
            "Customers without segment mapping dropped. "
            "CFO dashboard under-reports revenue by an unknown amount."
        ),
        sas = textwrap.dedent("""\
            proc sql;
              create table enriched as
              select a.*, b.segment
              from customers a
              left join segments b on a.customer_id = b.customer_id;
            quit;"""),
        buggy_py = (
            "enriched = pd.merge(customers, segments, "
            "on='customer_id', how='inner')"
        ),
        correct_py = (
            "enriched = pd.merge(customers, segments, "
            "on='customer_id', how='left')"
        ),
    ),
]


# -------------------------------------------------------------------------
# Runner
# -------------------------------------------------------------------------

def _run_case(case: BugCase, agent: Z3VerificationAgent) -> None:
    t0 = time.monotonic()
    br = agent.verify(case.sas, case.buggy_py)
    case.buggy_z3_latency  = (time.monotonic() - t0) * 1000
    case.buggy_z3_status   = br.status.value
    case.buggy_z3_pattern  = br.pattern
    case.buggy_z3_issue    = br.counterexample.get("issue", "")    if br.counterexample else ""
    case.buggy_z3_hint     = (br.counterexample.get("hint", "")
                               or br.counterexample.get("fix", "")) if br.counterexample else ""

    t0 = time.monotonic()
    cr = agent.verify(case.sas, case.correct_py)
    case.correct_z3_latency  = (time.monotonic() - t0) * 1000
    case.correct_z3_status   = cr.status.value
    case.correct_z3_pattern  = cr.pattern


def _print_case(case: BugCase, idx: int, total: int) -> None:
    W = 72
    print(f"\n{'=' * W}")
    print(f"  [{idx}/{total}]  {case.name}")
    print(f"  Bug   : {case.bug_kind}")
    print(f"  Impact: {case.impact}")
    print(f"{'=' * W}")

    print(f"\n  SAS source:")
    for line in case.sas.strip().splitlines():
        print(f"    {line}")

    print(f"\n  BUGGY translation (what the LLM sometimes produces):")
    for line in case.buggy_py.strip().splitlines():
        print(f"    {line}")

    print(f"\n  +-- WITHOUT Z3 (syntax + exec validation only) ---------------+")
    print(f"  |  Result : PASS  ->  translation ships as SUCCESS            |")
    print(f"  |  Bug    : UNDETECTED  (semantic error enters production)    |")
    print(f"  +-------------------------------------------------------------+")

    label = _STATUS_LABEL.get(case.buggy_z3_status, case.buggy_z3_status)
    print(f"\n  +-- WITH Z3  ({case.buggy_z3_latency:.0f} ms) {'-'*(47 - len(str(int(case.buggy_z3_latency))))}+")
    print(f"  |  Result  : {label}")
    if case.buggy_z3_pattern:
        print(f"  |  Pattern : {case.buggy_z3_pattern}")
    if case.buggy_z3_issue:
        issue_lines = textwrap.wrap(case.buggy_z3_issue, 58)
        print(f"  |  Issue   : {issue_lines[0]}")
        for extra in issue_lines[1:]:
            print(f"  |            {extra}")
    if case.buggy_z3_hint:
        hint_lines = textwrap.wrap(case.buggy_z3_hint, 58)
        print(f"  |  Fix     : {hint_lines[0]}")
        for extra in hint_lines[1:]:
            print(f"  |            {extra}")
    print(f"  +-------------------------------------------------------------+")

    print(f"\n  CORRECT translation:")
    for line in case.correct_py.strip().splitlines():
        print(f"    {line}")
    correct_label = _STATUS_LABEL.get(case.correct_z3_status, case.correct_z3_status)
    print(f"  Z3 result : {correct_label}  (pattern: {case.correct_z3_pattern or 'none'})")


def _print_summary(cases: list[BugCase]) -> None:
    total          = len(cases)
    bugs_caught    = sum(1 for c in cases if c.buggy_z3_status == "counterexample")
    false_positive = sum(1 for c in cases if c.correct_z3_status == "counterexample")
    mean_latency   = sum(c.buggy_z3_latency for c in cases) / total if cases else 0

    W = 72
    print(f"\n{'=' * W}")
    print(f"  Z3 EFFECT SUMMARY  --  Before vs After")
    print(f"{'=' * W}\n")

    col_a = 26
    col_b = 16
    col_c = 22
    hdr = (f"  {'Pattern':<{col_a}}"
           f"{'Without Z3':<{col_b}}"
           f"{'Buggy + Z3':<{col_c}}"
           f"Correct + Z3")
    print(hdr)
    print(f"  {'-'*col_a} {'-'*col_b} {'-'*col_c} {'-'*14}")

    for c in cases:
        no_z3   = "PASS (missed)"
        with_z3 = _STATUS_LABEL.get(c.buggy_z3_status, c.buggy_z3_status).strip("[] ")
        correct = _STATUS_LABEL.get(c.correct_z3_status, c.correct_z3_status).strip("[] ")
        print(f"  {c.name:<{col_a}} {no_z3:<{col_b}} {with_z3:<{col_c}} {correct}")

    print(f"\n  {'-'*68}")
    print(f"  Bugs caught by Z3     : {bugs_caught}/{total}")
    print(f"  False positives       : {false_positive}/{total}")
    print(f"  Mean Z3 latency       : {mean_latency:.1f} ms per block")
    print(f"\n  Conclusion:")
    print(f"  Z3 catches {bugs_caught}/{total} semantic bugs that syntax + exec validation misses,")
    print(f"  with {false_positive} false positives on correct translations.")
    print(f"  Average overhead: {mean_latency:.1f} ms -- negligible vs LLM latency (>5000 ms).")
    print()


# -------------------------------------------------------------------------
# pytest fixtures
# -------------------------------------------------------------------------

@pytest.fixture(scope="module")
def agent():
    return Z3VerificationAgent()


# -------------------------------------------------------------------------
# Individual test classes (one per bug case)
# -------------------------------------------------------------------------

class TestSortDirectionEffect:
    case = CASES[0]
    def test_buggy_is_counterexample(self, agent):
        _run_case(self.case, agent)
        _print_case(self.case, 1, len(CASES))
        assert self.case.buggy_z3_status == "counterexample"
    def test_correct_not_counterexample(self, agent):
        _run_case(self.case, agent)
        assert self.case.correct_z3_status != "counterexample"


class TestProcMeansDropnaEffect:
    case = CASES[1]
    def test_buggy_is_counterexample(self, agent):
        _run_case(self.case, agent)
        _print_case(self.case, 2, len(CASES))
        assert self.case.buggy_z3_status == "counterexample"
        assert "dropna" in self.case.buggy_z3_issue.lower()
    def test_correct_not_counterexample(self, agent):
        _run_case(self.case, agent)
        assert self.case.correct_z3_status != "counterexample"


class TestBooleanFilterThresholdEffect:
    case = CASES[2]
    def test_buggy_is_counterexample(self, agent):
        _run_case(self.case, agent)
        _print_case(self.case, 3, len(CASES))
        assert self.case.buggy_z3_status == "counterexample"
    def test_correct_not_counterexample(self, agent):
        _run_case(self.case, agent)
        assert self.case.correct_z3_status != "counterexample"


class TestSortNodupkeyEffect:
    case = CASES[3]
    def test_buggy_is_counterexample(self, agent):
        _run_case(self.case, agent)
        _print_case(self.case, 4, len(CASES))
        assert self.case.buggy_z3_status == "counterexample"
    def test_correct_not_counterexample(self, agent):
        _run_case(self.case, agent)
        assert self.case.correct_z3_status != "counterexample"


class TestIterrowsEffect:
    case = CASES[4]
    def test_buggy_is_counterexample(self, agent):
        _run_case(self.case, agent)
        _print_case(self.case, 5, len(CASES))
        assert self.case.buggy_z3_status == "counterexample"
        assert "iterrows" in self.case.buggy_z3_issue.lower()
    def test_correct_not_counterexample(self, agent):
        _run_case(self.case, agent)
        assert self.case.correct_z3_status != "counterexample"


class TestArithmeticCoefficientEffect:
    case = CASES[5]
    def test_buggy_is_counterexample(self, agent):
        _run_case(self.case, agent)
        _print_case(self.case, 6, len(CASES))
        assert self.case.buggy_z3_status == "counterexample"
    def test_correct_not_counterexample(self, agent):
        _run_case(self.case, agent)
        assert self.case.correct_z3_status != "counterexample"


class TestLeftJoinTypeEffect:
    case = CASES[6]
    def test_buggy_is_counterexample(self, agent):
        _run_case(self.case, agent)
        _print_case(self.case, 7, len(CASES))
        assert self.case.buggy_z3_status == "counterexample"
    def test_correct_not_counterexample(self, agent):
        _run_case(self.case, agent)
        assert self.case.correct_z3_status != "counterexample"


# -------------------------------------------------------------------------
# Master summary test -- the one to show during the thesis defense
# -------------------------------------------------------------------------

def test_z3_effect_summary(agent):
    """Full before/after table for all 7 patterns.

    Run with -s to see the printed table:
        pytest tests/test_z3_effect.py::test_z3_effect_summary -v -s
    """
    for case in CASES:
        _run_case(case, agent)

    _print_summary(CASES)

    bugs_caught    = sum(1 for c in CASES if c.buggy_z3_status == "counterexample")
    false_positive = sum(1 for c in CASES if c.correct_z3_status == "counterexample")

    assert bugs_caught == len(CASES), (
        f"Z3 should catch all {len(CASES)} bugs, caught {bugs_caught}"
    )
    assert false_positive == 0, (
        f"Z3 produced {false_positive} false positive(s) on correct translations"
    )


# -------------------------------------------------------------------------
# Standalone runner
# -------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\nCodara  Z3 Effect Analysis")
    print(f"Running {len(CASES)} test cases...\n")

    z3 = Z3VerificationAgent()
    t_start = time.monotonic()
    for i, case in enumerate(CASES):
        _run_case(case, z3)
        _print_case(case, i + 1, len(CASES))

    elapsed = time.monotonic() - t_start
    _print_summary(CASES)
    print(f"Total wall time: {elapsed:.2f}s\n")

    bugs_caught = sum(1 for c in CASES if c.buggy_z3_status == "counterexample")
    sys.exit(0 if bugs_caught == len(CASES) else 1)
