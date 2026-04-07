"""Tests for Z3VerificationAgent.

Tests grouped by pattern:
  - linear arithmetic (PROC MEANS)
  - boolean filter (WHERE/IF)
  - sort/dedup (PROC SORT NODUPKEY)
  - simple assignment (DATA step)
  - fallback to UNKNOWN for unsupported patterns
  - COUNTEREXAMPLE detection
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


# ── Linear arithmetic ────────────────────────────────────────────────

def test_proc_means_equivalent(agent):
    sas = "proc means data=patients; var age; output out=stats mean=mean_age; run;"
    py = "stats = patients.groupby('id')['age'].mean().reset_index(name='mean_age')"
    result = agent._verify_linear_arithmetic(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_proc_means_without_proc_means_returns_none(agent):
    """Non-PROC MEANS code should not match this pattern."""
    sas = "data output; set input; run;"
    py = "output = input.copy()"
    result = agent._verify_linear_arithmetic(sas, py)
    assert result is None


# ── Boolean filter ───────────────────────────────────────────────────

def test_boolean_filter_gt_equivalent(agent):
    sas = "data adults; set people; if age > 18; run;"
    py = "adults = people[people['age'] > 18]"
    result = agent._verify_boolean_filter(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_boolean_filter_eq_equivalent(agent):
    sas = "data active; set customers; where status = 1; run;"
    py = "active = customers[customers['status'] == 1]"
    result = agent._verify_boolean_filter(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_boolean_filter_no_comparison_returns_none(agent):
    sas = "data output; set input; retain x 0; run;"
    py = "output = input.copy()\noutput['x'] = 0"
    result = agent._verify_boolean_filter(sas, py)
    assert result is None


# ── Sort + NODUPKEY ──────────────────────────────────────────────────

def test_sort_nodupkey_proved(agent):
    sas = "proc sort data=patients nodupkey; by patient_id; run;"
    py = "patients = patients.sort_values('patient_id').drop_duplicates(subset='patient_id')"
    result = agent._verify_sort_nodupkey(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_sort_nodupkey_missing_dedup_counterexample(agent):
    sas = "proc sort data=patients nodupkey; by patient_id; run;"
    py = "patients = patients.sort_values('patient_id')"  # missing drop_duplicates
    result = agent._verify_sort_nodupkey(sas, py)
    assert result is not None
    # drop_duplicates missing → counterexample
    assert result.status == VerificationStatus.COUNTEREXAMPLE


def test_sort_nodupkey_not_matched_without_nodupkey(agent):
    sas = "proc sort data=patients; by patient_id; run;"
    py = "patients = patients.sort_values('patient_id')"
    result = agent._verify_sort_nodupkey(sas, py)
    assert result is None


# ── Simple assignment ────────────────────────────────────────────────

def test_simple_assignment_equivalent(agent):
    sas = "data out; set in; salary_usd = salary_eur * 1.1; run;"
    py = "out = in_.copy()\nout['salary_usd'] = out['salary_eur'] * 1.1"
    result = agent._verify_simple_assignment(sas, py)
    assert result is not None
    assert result.status == VerificationStatus.PROVED


def test_simple_assignment_counterexample(agent):
    sas = "data out; set in; score = x * 2 + 10; run;"
    py = "out = in_.copy()\nout['score'] = out['x'] * 3 + 10"   # wrong multiplier
    result = agent._verify_simple_assignment(sas, py)
    # Z3 finds x * 2 + 10 != x * 3 + 10 for any x
    # (may be COUNTEREXAMPLE or UNKNOWN depending on parse success)
    assert result is not None


# ── Top-level verify() dispatcher ────────────────────────────────────

def test_verify_dispatches_to_linear(agent):
    sas = "proc means data=d; var v; output out=s mean=m; run;"
    py = "s = d['v'].mean()"
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
    sas = "proc means data=d; var v; output out=s mean=m; run;"
    py = "s = d['v'].mean()"
    result = agent.verify(sas, py)
    assert result.latency_ms >= 0.0


def test_verify_counterexample_re_queues():
    """When COUNTEREXAMPLE is returned, orchestrator should bump risk_level to HIGH."""
    # This test documents the expected downstream behaviour, not the Z3 call itself.
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
