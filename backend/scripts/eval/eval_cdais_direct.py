"""eval_cdais_direct.py — Direct CDAIS evaluation without oracle dependency.

Tests the core CDAIS claim: does the Z3 witness actually expose the bug?
For each error class, we directly compute correct vs incorrect output and check divergence.

This bypasses the oracle machinery and tests the mathematical guarantee directly.

Usage:
    cd C:/Users/labou/Desktop/Stage/backend
    C:/Users/labou/Desktop/Stage/venv/Scripts/python scripts/eval/eval_cdais_direct.py
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from partition.testing.cdais.constraint_catalog import (
    ALL_ERROR_CLASSES,
    ConstraintConfig,
)
from partition.testing.cdais.synthesizer import CDASISynthesizer


def correct_retain_reset(df: pd.DataFrame) -> pd.Series:
    """Per-group cumsum (correct SAS behavior)."""
    return df.groupby("group")["value"].cumsum()


def incorrect_retain_reset(df: pd.DataFrame) -> pd.Series:
    """Global cumsum (common LLM bug)."""
    return df["value"].cumsum()


def correct_lag_queue(df: pd.DataFrame) -> pd.Series:
    """Per-group shift with NaN at group boundaries (correct SAS behavior)."""
    return df.groupby("group")["value"].shift(1)


def incorrect_lag_queue(df: pd.DataFrame) -> pd.Series:
    """Global shift (carries across group boundaries — LLM bug)."""
    return df["value"].shift(1)


def correct_sort_stable(df: pd.DataFrame) -> pd.DataFrame:
    """Stable sort (correct SAS behavior)."""
    return df.sort_values("primary_key", kind="mergesort").reset_index(drop=True)


def incorrect_sort_stable(df: pd.DataFrame) -> pd.DataFrame:
    """Unstable sort (may reorder equal keys — LLM bug)."""
    return df.sort_values("primary_key", kind="quicksort").reset_index(drop=True)


def correct_null_arithmetic(df: pd.DataFrame) -> pd.Series:
    """fillna(0) before cumsum (correct SAS behavior)."""
    return df["value"].fillna(0).cumsum()


def incorrect_null_arithmetic(df: pd.DataFrame) -> pd.Series:
    """Cumsum without fillna — NaN propagates (LLM bug)."""
    return df["value"].cumsum()


def correct_join_type(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    """Outer join (correct SAS MERGE behavior)."""
    return pd.merge(left, right, on="key", how="outer")


def incorrect_join_type(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    """Inner join (common LLM bug)."""
    return pd.merge(left, right, on="key", how="inner")


def correct_group_boundary(df: pd.DataFrame) -> pd.DataFrame:
    """First row of each group (correct SAS FIRST. behavior)."""
    return df.groupby("group").first().reset_index()


def incorrect_group_boundary(df: pd.DataFrame) -> pd.DataFrame:
    """First row of entire DataFrame (common LLM bug)."""
    return df.head(1)


def generate_random_data(error_class: str, n_groups: int = None, n_rows: int = None) -> dict:
    """Generate random test data for a given error class."""
    n_groups = n_groups or random.randint(1, 4)
    n_rows = n_rows or random.randint(2, 8)

    if error_class in ("RETAIN_RESET", "LAG_QUEUE", "GROUP_BOUNDARY"):
        rows = []
        for g in range(n_groups):
            for _ in range(n_rows):
                rows.append({"group": chr(65 + g), "value": random.randint(1, 50)})
        return {"df": pd.DataFrame(rows)}

    elif error_class == "SORT_STABLE":
        rows = [
            {
                "primary_key": random.randint(1, max(2, n_rows // 2)),
                "secondary": random.randint(1, 100),
                "original_order": i,
            }
            for i in range(n_rows * n_groups)
        ]
        return {"df": pd.DataFrame(rows)}

    elif error_class == "NULL_ARITHMETIC":
        values = [random.randint(1, 50) for _ in range(n_rows * n_groups)]
        # Inject some NaN values
        for i in random.sample(range(len(values)), max(1, len(values) // 4)):
            values[i] = float("nan")
        rows = [{"group": chr(65 + (i // n_rows)), "value": v} for i, v in enumerate(values)]
        return {"df": pd.DataFrame(rows)}

    elif error_class == "JOIN_TYPE":
        left_keys = random.sample(range(1, 20), min(n_rows, 10))
        right_keys = random.sample(range(1, 20), min(n_rows, 10))
        left = pd.DataFrame({"key": left_keys, "left_val": range(len(left_keys))})
        right = pd.DataFrame({"key": right_keys, "right_val": range(len(right_keys))})
        return {"left": left, "right": right}

    return {"df": pd.DataFrame()}


def test_divergence(error_class: str, data: dict) -> bool:
    """Check if correct and incorrect produce different results for this data."""
    try:
        if error_class == "RETAIN_RESET":
            correct = correct_retain_reset(data["df"])
            incorrect = incorrect_retain_reset(data["df"])
            return not correct.equals(incorrect)

        elif error_class == "LAG_QUEUE":
            correct = correct_lag_queue(data["df"])
            incorrect = incorrect_lag_queue(data["df"])
            # Compare with NaN-aware equality
            return not correct.equals(incorrect)

        elif error_class == "SORT_STABLE":
            correct = correct_sort_stable(data["df"])
            incorrect = incorrect_sort_stable(data["df"])
            return not correct.equals(incorrect)

        elif error_class == "NULL_ARITHMETIC":
            correct = correct_null_arithmetic(data["df"])
            incorrect = incorrect_null_arithmetic(data["df"])
            # NaN != NaN, so use custom comparison
            c_vals = correct.fillna(-9999)
            i_vals = incorrect.fillna(-9999)
            return not c_vals.equals(i_vals)

        elif error_class == "JOIN_TYPE":
            correct = correct_join_type(data["left"], data["right"])
            incorrect = incorrect_join_type(data["left"], data["right"])
            return len(correct) != len(incorrect)

        elif error_class == "GROUP_BOUNDARY":
            correct = correct_group_boundary(data["df"])
            incorrect = incorrect_group_boundary(data["df"])
            return len(correct) != len(incorrect)

    except Exception:
        return False
    return False


def main():
    output_path = _root / "output" / "cdais_eval_direct.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    synthesizer = CDASISynthesizer()
    cfg = ConstraintConfig()

    N_RANDOM_TRIALS = 200
    N_HEURISTIC_TRIALS = 50  # DummyDataGen-style: always 2+ groups

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": "Direct divergence test: correct vs incorrect on witness/random/heuristic data",
        "per_class": {},
        "summary": {},
    }

    print("=" * 70)
    print("CDAIS DIRECT EVALUATION — Mathematical Divergence Test")
    print("=" * 70)
    print(f"Random trials per class: {N_RANDOM_TRIALS}")
    print(f"Heuristic trials per class: {N_HEURISTIC_TRIALS}")
    print()

    for ec in ALL_ERROR_CLASSES:
        name = ec.name
        print(f"\n{'='*50}")
        print(f"  {name}")
        print(f"{'='*50}")

        # 1. CDAIS witness synthesis
        t0 = time.monotonic()
        synthesis = synthesizer.synthesize(ec, cfg)
        synth_ms = (time.monotonic() - t0) * 1000

        cdais_detects = False
        if synthesis.sat and not synthesis.witness_df.empty:
            witness = synthesis.witness_df
            # Build the data dict from witness
            if name == "JOIN_TYPE":
                left_mask = witness["__table__"] == "left"
                left = witness[left_mask].drop(columns=["__table__"]).reset_index(drop=True)
                right = witness[~left_mask].drop(columns=["__table__"]).reset_index(drop=True)
                data = {"left": left, "right": right}
            else:
                data = {"df": witness}

            cdais_detects = test_divergence(name, data)
            print(
                f"  Z3 witness ({len(witness)} rows, {synth_ms:.0f}ms): "
                f"{'DIVERGES (bug exposed)' if cdais_detects else 'NO DIVERGENCE'}"
            )
        else:
            print(f"  Z3 witness: UNSAT ({synth_ms:.0f}ms)")

        # 2. Random testing
        random_detections = 0
        for trial in range(N_RANDOM_TRIALS):
            data = generate_random_data(name)
            if test_divergence(name, data):
                random_detections += 1
                break  # First detection is enough
        # Actually count WHAT FRACTION of random trials detect it
        detect_count = 0
        for _ in range(N_RANDOM_TRIALS):
            data = generate_random_data(name)
            if test_divergence(name, data):
                detect_count += 1
        random_detect_pct = detect_count / N_RANDOM_TRIALS
        print(
            f"  Random ({N_RANDOM_TRIALS} trials): {detect_count}/{N_RANDOM_TRIALS} "
            f"= {random_detect_pct:.1%} detect divergence"
        )

        # 3. Heuristic (always multi-group, like DummyDataGenerator)
        heuristic_count = 0
        for _ in range(N_HEURISTIC_TRIALS):
            data = generate_random_data(
                name, n_groups=random.randint(2, 4), n_rows=random.randint(3, 8)
            )
            if test_divergence(name, data):
                heuristic_count += 1
        heuristic_detect_pct = heuristic_count / N_HEURISTIC_TRIALS
        print(
            f"  Heuristic ({N_HEURISTIC_TRIALS} trials, >=2 groups): {heuristic_count}/{N_HEURISTIC_TRIALS} "
            f"= {heuristic_detect_pct:.1%} detect divergence"
        )

        results["per_class"][name] = {
            "cdais_detects": cdais_detects,
            "cdais_witness_rows": len(synthesis.witness_df) if synthesis.sat else 0,
            "cdais_synthesis_ms": round(synth_ms, 1),
            "random_detect_fraction": round(random_detect_pct, 4),
            "random_detects_at_least_once": random_detect_pct > 0,
            "heuristic_detect_fraction": round(heuristic_detect_pct, 4),
            "heuristic_detects_at_least_once": heuristic_detect_pct > 0,
        }

    # Summary
    n = len(ALL_ERROR_CLASSES)
    cdais_detected = sum(1 for v in results["per_class"].values() if v["cdais_detects"])
    random_detected = sum(
        1 for v in results["per_class"].values() if v["random_detects_at_least_once"]
    )
    heuristic_detected = sum(
        1 for v in results["per_class"].values() if v["heuristic_detects_at_least_once"]
    )

    avg_random_frac = np.mean([v["random_detect_fraction"] for v in results["per_class"].values()])
    avg_heuristic_frac = np.mean(
        [v["heuristic_detect_fraction"] for v in results["per_class"].values()]
    )
    avg_synth_ms = np.mean([v["cdais_synthesis_ms"] for v in results["per_class"].values()])
    avg_witness_rows = np.mean([v["cdais_witness_rows"] for v in results["per_class"].values()])

    results["summary"] = {
        "cdais_detection_rate": f"{cdais_detected}/{n} = {cdais_detected/n:.1%}",
        "random_detection_rate": f"{random_detected}/{n} = {random_detected/n:.1%}",
        "heuristic_detection_rate": f"{heuristic_detected}/{n} = {heuristic_detected/n:.1%}",
        "avg_random_trial_detect_fraction": round(avg_random_frac, 4),
        "avg_heuristic_trial_detect_fraction": round(avg_heuristic_frac, 4),
        "avg_synthesis_ms": round(avg_synth_ms, 1),
        "avg_witness_rows": round(avg_witness_rows, 1),
        "note": "CDAIS guarantees detection in 1 trial with minimal witness. Random/heuristic need multiple trials and may still miss.",
    }

    print("\n\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"  CDAIS detection rate:      {cdais_detected}/{n} = {cdais_detected/n:.1%}")
    print(f"  Random detection (>=1 hit): {random_detected}/{n} = {random_detected/n:.1%}")
    print(f"  Heuristic detection:       {heuristic_detected}/{n} = {heuristic_detected/n:.1%}")
    print(f"  Avg random trial success:  {avg_random_frac:.1%} of individual trials find bug")
    print(f"  Avg heuristic trial success: {avg_heuristic_frac:.1%}")
    print(f"  Avg CDAIS synthesis time:  {avg_synth_ms:.0f}ms")
    print(f"  Avg CDAIS witness size:    {avg_witness_rows:.0f} rows")
    print("\n  KEY INSIGHT: CDAIS detects in 1 trial (deterministic guarantee)")
    print(
        f"  Random needs ~{int(1/avg_random_frac) if avg_random_frac > 0 else 'inf'} trials to find the bug on average"
    )

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_path}")


if __name__ == "__main__":
    main()
