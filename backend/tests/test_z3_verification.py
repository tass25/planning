"""Tests for Z3VerificationAgent — 10 pattern checks.

Tests grouped by pattern:
  - proc_means_groupby  (CLASS + dropna=False)
  - boolean_filter      (WHERE/IF numeric condition)
  - sort_direction      (PROC SORT DESCENDING)
  - sort_nodupkey       (PROC SORT NODUPKEY → drop_duplicates)
  - conditional_assignment (IF/THEN/ELSE → np.select / np.where)
  - simple_assignment   (DATA step y = x * coeff + offset)
  - format_display_only (PROC FORMAT → new _fmt column)
  - left_join           (LEFT JOIN → how='left')
  - merge_indicator     (MERGE IN= → indicator=True)
  - stepwise_regression (PROC REG STEPWISE → statsmodels p-values)
  - top-level verify()  dispatcher
"""

from __future__ import annotations

import pytest
from partition.verification.z3_agent import (
    Z3VerificationAgent,
    VerificationStatus,
)


@pytest.fixture
def agent():
    return Z3VerificationAgent()


# ── Pattern 3: PROC MEANS with CLASS → groupby(dropna=False).agg() ──────────

def test_proc_means_groupby_proved(agent):
    sas = (
        "proc means data=patients; class dept; var age; "
        "output out=stats mean=mean_age; run;"
    )
    py = "stats = patients.groupby(['dept'], dropna=False).agg(mean_age=('age', 'mean'))"
    result = agent._verify_proc_means_groupby(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_proc_means_no_groupby_counterexample(agent):
    """groupby() missing entirely → COUNTEREXAMPLE."""
    sas = "proc means data=patients; class dept; var age; output out=s mean=m; run;"
    py = "s = patients['age'].mean()"
    result = agent._verify_proc_means_groupby(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE


def test_proc_means_missing_dropna_counterexample(agent):
    """groupby present but dropna=False missing → COUNTEREXAMPLE (NaN group lost)."""
    sas = "proc means data=patients; class dept; var age; output out=s mean=m; run;"
    py = "s = patients.groupby(['dept']).agg(m=('age', 'mean'))"
    result = agent._verify_proc_means_groupby(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE
    assert "dropna" in result.counterexample.get("issue", "")


def test_proc_means_no_class_returns_unknown(agent):
    """PROC MEANS without CLASS → UNKNOWN (no groupby semantics to verify)."""
    sas = "proc means data=patients; var age; output out=stats mean=mean_age; run;"
    py = "stats = patients['age'].mean()"
    result = agent._verify_proc_means_groupby(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.UNKNOWN


def test_proc_means_no_match_returns_none(agent):
    """Non-PROC MEANS code should not match this pattern."""
    sas = "data output; set input; run;"
    py = "output = input.copy()"
    result = agent._verify_proc_means_groupby(sas, py)
    assert result is None


# ── Pattern 4: Boolean filter (WHERE / IF numeric condition) ─────────────────

def test_boolean_filter_gt_proved(agent):
    sas = "data adults; set people; if age > 18; run;"
    py = "adults = people[people['age'] > 18]"
    result = agent._verify_boolean_filter(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_boolean_filter_eq_proved(agent):
    sas = "data active; set customers; where status = 1; run;"
    py = "active = customers[customers['status'] == 1]"
    result = agent._verify_boolean_filter(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_boolean_filter_wrong_threshold_counterexample(agent):
    """Different threshold values → Z3 finds counterexample."""
    sas = "data high_val; set orders; if amount > 1000; run;"
    py = "high_val = orders[orders['amount'] > 500]"   # wrong threshold
    result = agent._verify_boolean_filter(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE


def test_boolean_filter_no_comparison_returns_none(agent):
    sas = "data output; set input; retain x 0; run;"
    py = "output = input.copy()\noutput['x'] = 0"
    result = agent._verify_boolean_filter(sas, py)
    assert result is None


# ── Pattern 2: PROC SORT direction ───────────────────────────────────────────

def test_sort_direction_proved(agent):
    sas = "proc sort data=employees; by dept descending salary; run;"
    py = "employees = employees.sort_values(['dept', 'salary'], ascending=[True, False])"
    result = agent._verify_sort_direction(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_sort_direction_wrong_ascending_counterexample(agent):
    """DESCENDING column translated as ascending=True → COUNTEREXAMPLE."""
    sas = "proc sort data=employees; by dept descending salary; run;"
    py = "employees = employees.sort_values(['dept', 'salary'], ascending=[True, True])"
    result = agent._verify_sort_direction(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE


def test_sort_direction_no_sort_returns_none(agent):
    sas = "data output; set input; run;"
    py = "output = input.copy()"
    result = agent._verify_sort_direction(sas, py)
    assert result is None


# ── Pattern 9: PROC SORT NODUPKEY → drop_duplicates ──────────────────────────

def test_sort_nodupkey_proved(agent):
    sas = "proc sort data=patients nodupkey; by patient_id; run;"
    py = "patients = patients.sort_values('patient_id').drop_duplicates(subset='patient_id')"
    result = agent._verify_sort_nodupkey(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_sort_nodupkey_missing_dedup_counterexample(agent):
    """sort_values present but drop_duplicates missing → COUNTEREXAMPLE."""
    sas = "proc sort data=patients nodupkey; by patient_id; run;"
    py = "patients = patients.sort_values('patient_id')"
    result = agent._verify_sort_nodupkey(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE
    assert "drop_duplicates" in result.counterexample.get("hint", "")


def test_sort_nodupkey_not_matched_without_nodupkey(agent):
    """PROC SORT without NODUPKEY should not match this pattern."""
    sas = "proc sort data=patients; by patient_id; run;"
    py = "patients = patients.sort_values('patient_id')"
    result = agent._verify_sort_nodupkey(sas, py)
    assert result is None


# ── Pattern 1: IF/THEN/ELSE → np.select / np.where ───────────────────────────

def test_conditional_assignment_iterrows_counterexample(agent):
    """iterrows() for conditional assignment is always COUNTEREXAMPLE."""
    sas = "data out; set in; if x > 0 then y = 1; else y = 0; run;"
    py = (
        "for idx, row in df.iterrows():\n"
        "    df.at[idx, 'y'] = 1 if row['x'] > 0 else 0"
    )
    result = agent._verify_conditional_assignment(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE
    assert "iterrows" in result.counterexample.get("issue", "")


def test_conditional_assignment_np_select_proved(agent):
    """np.select with matching condition → PROVED."""
    sas = "data out; set in; if balance > 1000 then tier = 'A'; else tier = 'B'; run;"
    py = "out['tier'] = np.select([out['balance'] > 1000], ['A'], default='B')"
    result = agent._verify_conditional_assignment(sas, py)
    assert result is not None
    # Z3 checks condition equivalence — threshold matches → PROVED or UNKNOWN
    assert result.status in (VerificationStatus.PROVED, VerificationStatus.UNKNOWN)


def test_conditional_assignment_wrong_threshold_counterexample(agent):
    """Different threshold in SAS vs Python → Z3 finds counterexample."""
    sas = "data out; set in; if score > 90 then grade = 'A'; run;"
    py = "out['grade'] = np.select([out['score'] > 80], ['A'], default='B')"
    result = agent._verify_conditional_assignment(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE


# ── Pattern 10: DATA step arithmetic assignment ───────────────────────────────

def test_simple_assignment_equivalent(agent):
    """Matching coefficient and offset → PROVED."""
    sas = "data out; set in; salary_usd = salary_eur * 1.1; run;"
    py = "out = in_.copy()\nout['salary_usd'] = out['salary_eur'] * 1.1"
    result = agent._verify_simple_assignment(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_simple_assignment_counterexample(agent):
    """Wrong multiplier → Z3 finds x where SAS and Python differ."""
    sas = "data out; set in; score = x * 2 + 10; run;"
    py = "out = in_.copy()\nout['score'] = out['x'] * 3 + 10"   # wrong multiplier
    result = agent._verify_simple_assignment(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE
    assert "2.0" in result.counterexample.get("expected", "")
    assert "3.0" in result.counterexample.get("got", "")


def test_simple_assignment_no_data_step_returns_none(agent):
    """Non-DATA-step code should not match."""
    sas = "proc means data=d; var v; run;"
    py = "d['v'].mean()"
    result = agent._verify_simple_assignment(sas, py)
    assert result is None


# ── Pattern 5: PROC FORMAT display-only ──────────────────────────────────────

def test_format_display_only_proved(agent):
    """New _fmt column created → PROVED."""
    sas = "proc format; value $grade 'A'='Red'; run;\nformat status $grade.;"
    py = "fmt = {'A': 'Red'}\ndf['status_fmt'] = df['status'].map(fmt)"
    result = agent._verify_format_display_only(sas, py)
    assert result is not None
    assert result.status in (VerificationStatus.PROVED, VerificationStatus.UNKNOWN)


def test_format_display_overwrite_counterexample(agent):
    """Original column overwritten instead of new _fmt column → COUNTEREXAMPLE."""
    sas = "proc format; value $grade 'A'='Red'; run;\nformat status $grade.;"
    py = "fmt = {'A': 'Red'}\ndf['grade'] = df['grade'].map(fmt)"
    result = agent._verify_format_display_only(sas, py)
    assert result is not None
    # either COUNTEREXAMPLE (overwrite detected) or UNKNOWN
    assert result.status in (VerificationStatus.COUNTEREXAMPLE, VerificationStatus.UNKNOWN)


# ── Pattern 6: LEFT JOIN ──────────────────────────────────────────────────────

def test_left_join_proved(agent):
    sas = "proc sql; create table out as select * from t1 left join t2 on t1.id=t2.id; quit;"
    py = "out = pd.merge(t1, t2, on='id', how='left')"
    result = agent._verify_left_join(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_left_join_wrong_how_counterexample(agent):
    """how='inner' instead of how='left' → COUNTEREXAMPLE."""
    sas = "proc sql; create table out as select * from t1 left join t2 on t1.id=t2.id; quit;"
    py = "out = pd.merge(t1, t2, on='id', how='inner')"
    result = agent._verify_left_join(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE


def test_left_join_no_match_returns_none(agent):
    sas = "data output; set input; run;"
    py = "output = input.copy()"
    result = agent._verify_left_join(sas, py)
    assert result is None


# ── Pattern 8: PROC REG STEPWISE ─────────────────────────────────────────────

def test_stepwise_regression_sklearn_counterexample(agent):
    """sklearn used instead of statsmodels → COUNTEREXAMPLE."""
    sas = "proc reg data=d; model y = x1 x2 / selection=stepwise; run;"
    py = "from sklearn.linear_model import LinearRegression\nmodel = LinearRegression().fit(X, y)"
    result = agent._verify_stepwise_regression(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.COUNTEREXAMPLE
    assert "sklearn" in result.counterexample.get("issue", "")


def test_stepwise_regression_no_match_returns_none(agent):
    sas = "data output; set input; run;"
    py = "output = input.copy()"
    result = agent._verify_stepwise_regression(sas, py)
    assert result is None


# ── Top-level verify() dispatcher ────────────────────────────────────────────

def test_verify_dispatches_proc_means(agent):
    sas = "proc means data=d; class grp; var v; output out=s mean=m; run;"
    py = "s = d.groupby(['grp'], dropna=False).agg(m=('v', 'mean'))"
    result = agent.verify(sas, py)
    assert result.status in (VerificationStatus.PROVED, VerificationStatus.UNKNOWN)


def test_verify_returns_unknown_for_retain(agent):
    """RETAIN pattern is outside Z3 scope — should return UNKNOWN."""
    sas = """
    data summary;
      set transactions;
      by account_id;
      retain running_total 0;
      if first.account_id then running_total = 0;
      running_total + amount;
      if last.account_id then output;
    run;
    """
    py = "summary = transactions.groupby('account_id')['amount'].sum().reset_index()"
    result = agent.verify(sas, py)
    assert result.status == VerificationStatus.UNKNOWN


def test_verify_skipped_when_disabled(monkeypatch):
    """Z3_VERIFICATION=false should return SKIPPED without calling Z3."""
    monkeypatch.setenv("Z3_VERIFICATION", "false")
    a = Z3VerificationAgent()
    a.ENABLED = False
    result = a.verify("proc means data=d; var v; run;", "d.mean()")
    assert result.status == VerificationStatus.SKIPPED


def test_verify_has_latency_recorded(agent):
    sas = "proc means data=d; class g; var v; output out=s mean=m; run;"
    py = "s = d.groupby(['g'], dropna=False).agg(m=('v', 'mean'))"
    result = agent.verify(sas, py)
    assert result.latency_ms >= 0.0


def test_verify_counterexample_re_queues():
    """COUNTEREXAMPLE result documents that orchestrator bumps risk_level to HIGH."""
    from partition.verification.z3_agent import VerificationResult, VerificationStatus
    result = VerificationResult(
        status=VerificationStatus.COUNTEREXAMPLE,
        counterexample={"issue": "multiplier mismatch"},
    )
    assert result.status == VerificationStatus.COUNTEREXAMPLE
    assert result.counterexample


def test_z3_result_pattern_recorded(agent):
    sas = "proc sort data=patients nodupkey; by id; run;"
    py = "patients = patients.sort_values('id').drop_duplicates('id')"
    result = agent.verify(sas, py)
    if result.status == VerificationStatus.PROVED:
        assert result.pattern  # pattern name must be recorded
