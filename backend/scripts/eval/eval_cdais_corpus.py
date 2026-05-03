"""eval_cdais_corpus.py — Evaluate CDAIS detection rate on the gold corpus.

Produces REAL numbers for the paper by running CDAIS against known-bad
translations (each error class's canonical bug) and known-good translations.

For each gold pair:
  1. Check applicable error classes
  2. Synthesize witnesses
  3. Run oracle on the correct gold translation (should PASS → certificate)
  4. Run oracle on a known-BAD translation (should FAIL → detection)

Also compares with:
  - Random testing (random inputs, check oracle vs actual)
  - Heuristic adversarial (DummyDataGenerator inputs)

Output: JSON file with all results → directly usable in the paper tables.

Usage:
    cd backend
    python scripts/eval/eval_cdais_corpus.py
    python scripts/eval/eval_cdais_corpus.py --gold-dir knowledge_base/gold_standard --output output/cdais_eval.json
"""

from __future__ import annotations

import argparse
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

from partition.testing.cdais.cdais_runner import CDAISRunner
from partition.testing.cdais.constraint_catalog import (
    ALL_ERROR_CLASSES,
    ConstraintConfig,
    applicable_classes,
)
from partition.testing.cdais.synthesizer import CDASISynthesizer
from partition.translation.dummy_data_generator import DummyDataGenerator
from partition.translation.semantic_validator import (
    _compare_frames,
    _oracle_first_last,
    _oracle_lag,
    _oracle_merge,
    _oracle_proc_freq,
    _oracle_proc_means,
    _oracle_proc_sort,
    _oracle_retain,
)

ORACLE_FNS = [
    _oracle_proc_sort,
    _oracle_proc_means,
    _oracle_proc_freq,
    _oracle_retain,
    _oracle_lag,
    _oracle_first_last,
    _oracle_merge,
]

# Canonical BAD translations for each error class
BAD_TRANSLATIONS = {
    "RETAIN_RESET": """
import pandas as pd
df = input.copy()
df['total'] = df['value'].cumsum()  # BUG: no per-group reset
output = df
""",
    "LAG_QUEUE": """
import pandas as pd
df = input.copy()
df['lag_value'] = df['value'].shift(1)  # BUG: no group reset
output = df
""",
    "SORT_STABLE": """
import pandas as pd
df = input.copy()
output = df.sort_values('primary_key', kind='quicksort')  # BUG: unstable
""",
    "NULL_ARITHMETIC": """
import pandas as pd
df = input.copy()
df['running'] = df['value'].cumsum()  # BUG: NaN propagates
output = df
""",
    "JOIN_TYPE": """
import pandas as pd
output = pd.merge(left, right, on='key', how='inner')  # BUG: should be outer
""",
    "GROUP_BOUNDARY": """
import pandas as pd
df = input.copy()
output = df.head(1)  # BUG: should be first row of EACH group
""",
}

# Canonical GOOD translations for each error class
GOOD_TRANSLATIONS = {
    "RETAIN_RESET": """
import pandas as pd
df = input.copy()
df['total'] = df.groupby('group')['value'].cumsum()
output = df
""",
    "LAG_QUEUE": """
import pandas as pd
import numpy as np
df = input.copy()
df['lag_value'] = df.groupby('group')['value'].shift(1)
output = df
""",
    "SORT_STABLE": """
import pandas as pd
df = input.copy()
output = df.sort_values('primary_key', kind='mergesort')
""",
    "NULL_ARITHMETIC": """
import pandas as pd
df = input.copy()
df['running'] = df['value'].fillna(0).cumsum()
output = df
""",
    "JOIN_TYPE": """
import pandas as pd
output = pd.merge(left, right, on='key', how='outer')
""",
    "GROUP_BOUNDARY": """
import pandas as pd
df = input.copy()
output = df.groupby('group').first().reset_index()
""",
}

# SAS code samples that trigger each error class
SAS_TRIGGERS = {
    "RETAIN_RESET": """data output; set sales; by group; retain total 0;
if first.group then total = 0; total + value; run;""",
    "LAG_QUEUE": """data output; set input; by group; prev = lag(value); run;""",
    "SORT_STABLE": """proc sort data=input out=output; by primary_key; run;""",
    "NULL_ARITHMETIC": """data output; set input; retain running 0;
running + value; run;""",
    "JOIN_TYPE": """data output; merge left right; by key; run;""",
    "GROUP_BOUNDARY": """data output; set input; by group;
if first.group; run;""",
}


def run_oracle(sas_code: str, input_frames: dict) -> pd.DataFrame | None:
    for fn in ORACLE_FNS:
        try:
            result = fn(sas_code, input_frames)
            if result is not None:
                return next(iter(result.values()))
        except Exception:
            pass
    return None


def exec_python(code: str, input_frames: dict) -> pd.DataFrame | None:
    namespace = {"pd": pd, "np": np}
    for name, df in input_frames.items():
        namespace[name] = df.copy()
    if "input" in input_frames:
        namespace["df"] = input_frames["input"].copy()
    try:
        exec(code, namespace)  # noqa: S102
        for k, v in namespace.items():
            if (
                isinstance(v, pd.DataFrame)
                and k not in input_frames
                and not k.startswith("_")
                and k not in ("pd", "np", "df")
            ):
                return v
        if "output" in namespace and isinstance(namespace["output"], pd.DataFrame):
            return namespace["output"]
    except Exception:
        pass
    return None


def random_test_one(sas_code: str, python_code: str, n_samples: int = 100) -> bool:
    """Test with random data. Returns True if divergence detected."""
    for _ in range(n_samples):
        n_groups = random.randint(1, 4)
        n_rows = random.randint(2, 10)
        rows = []
        groups = [chr(65 + g) for g in range(n_groups)]
        for g in groups:
            for _ in range(n_rows):
                rows.append({"group": g, "value": random.randint(-50, 100)})
        df = pd.DataFrame(rows)
        input_frames = {"input": df}
        if "merge" in sas_code.lower():
            left = pd.DataFrame(
                {
                    "key": random.sample(range(1, 20), min(5, 19)),
                    "left_val": [random.randint(1, 100) for _ in range(5)],
                }
            )
            right = pd.DataFrame(
                {
                    "key": random.sample(range(1, 20), min(5, 19)),
                    "right_val": [random.randint(1, 100) for _ in range(5)],
                }
            )
            input_frames = {"left": left, "right": right}
        elif "proc sort" in sas_code.lower():
            rows2 = [
                {
                    "primary_key": random.randint(1, 3),
                    "secondary": random.randint(1, 100),
                    "original_order": i,
                }
                for i in range(n_rows)
            ]
            df = pd.DataFrame(rows2)
            input_frames = {"input": df}

        oracle_out = run_oracle(sas_code, input_frames)
        if oracle_out is None:
            continue
        actual_out = exec_python(python_code, input_frames)
        if actual_out is None:
            return True
        matched, _ = _compare_frames(oracle_out, actual_out)
        if not matched:
            return True
    return False


def heuristic_test_one(sas_code: str, python_code: str) -> bool:
    """Test with DummyDataGenerator adversarial data. Returns True if divergence detected."""
    try:
        gen = DummyDataGenerator(sas_code=sas_code)
        frames = gen.generate()
        if not frames:
            return False
        input_frames = frames
        oracle_out = run_oracle(sas_code, input_frames)
        if oracle_out is None:
            return False
        actual_out = exec_python(python_code, input_frames)
        if actual_out is None:
            return True
        matched, _ = _compare_frames(oracle_out, actual_out)
        return not matched
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Evaluate CDAIS on gold corpus")
    parser.add_argument("--gold-dir", default=str(_root / "knowledge_base" / "gold_standard"))
    parser.add_argument("--output", default=str(_root / "output" / "cdais_eval.json"))
    parser.add_argument("--random-samples", type=int, default=100)
    args = parser.parse_args()

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)

    synthesizer = CDASISynthesizer()
    runner = CDAISRunner()
    cfg = ConstraintConfig()

    results = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": "Evaluate CDAIS vs random vs heuristic on canonical bad translations",
        "per_class": {},
        "synthesis_times_ms": [],
        "summary": {},
    }

    print("=" * 70)
    print("CDAIS EVALUATION — Real Numbers")
    print("=" * 70)

    # For each error class: test CDAIS, random, heuristic
    for ec in ALL_ERROR_CLASSES:
        class_name = ec.name
        sas_code = SAS_TRIGGERS.get(class_name, "")
        bad_code = BAD_TRANSLATIONS.get(class_name, "")
        good_code = GOOD_TRANSLATIONS.get(class_name, "")

        print(f"\n--- {class_name} ---")

        class_result = {
            "applicable": ec.applicable_to(sas_code),
            "cdais_detects_bad": False,
            "cdais_certifies_good": False,
            "cdais_false_positive": False,
            "random_detects_bad": False,
            "heuristic_detects_bad": False,
            "synthesis_time_ms": 0.0,
            "witness_rows": 0,
        }

        # CDAIS synthesis
        t0 = time.monotonic()
        synthesis = synthesizer.synthesize(ec, cfg)
        synthesis_ms = (time.monotonic() - t0) * 1000
        class_result["synthesis_time_ms"] = round(synthesis_ms, 1)
        results["synthesis_times_ms"].append(synthesis_ms)

        if synthesis.sat:
            class_result["witness_rows"] = len(synthesis.witness_df)
            print(
                f"  Z3 synthesis: SAT in {synthesis_ms:.1f}ms, witness={len(synthesis.witness_df)} rows"
            )

            # Test CDAIS on bad translation
            report_bad = runner.run_on_code(sas_code, bad_code)
            class_result["cdais_detects_bad"] = not report_bad.all_passed
            print(
                f"  CDAIS on BAD translation: {'DETECTED' if not report_bad.all_passed else 'MISSED'}"
            )

            # Test CDAIS on good translation
            report_good = runner.run_on_code(sas_code, good_code)
            class_result["cdais_certifies_good"] = report_good.all_passed
            class_result["cdais_false_positive"] = not report_good.all_passed
            print(
                f"  CDAIS on GOOD translation: {'CERTIFIED' if report_good.all_passed else 'FALSE POSITIVE'}"
            )
        else:
            print(f"  Z3 synthesis: UNSAT/timeout ({synthesis_ms:.1f}ms)")

        # Random testing on bad translation
        random_detected = random_test_one(sas_code, bad_code, n_samples=args.random_samples)
        class_result["random_detects_bad"] = random_detected
        print(
            f"  Random ({args.random_samples} samples) on BAD: {'DETECTED' if random_detected else 'MISSED'}"
        )

        # Heuristic testing on bad translation
        heuristic_detected = heuristic_test_one(sas_code, bad_code)
        class_result["heuristic_detects_bad"] = heuristic_detected
        print(
            f"  Heuristic (DummyDataGen) on BAD: {'DETECTED' if heuristic_detected else 'MISSED'}"
        )

        results["per_class"][class_name] = class_result

    # Also run on gold corpus pairs (check how many get certificates)
    print("\n\n" + "=" * 70)
    print("GOLD CORPUS — CDAIS Certificate Statistics")
    print("=" * 70)

    gold_dir = Path(args.gold_dir)
    corpus_stats = {
        "total_pairs": 0,
        "pairs_with_applicable_classes": 0,
        "total_classes_checked": 0,
        "total_certificates_issued": 0,
        "total_failures": 0,
        "pairs_with_certificate": 0,
    }

    sas_files = sorted(gold_dir.glob("*.sas"))
    for sas_file in sas_files:
        json_file = sas_file.with_suffix(".gold.json")
        if not json_file.exists():
            continue
        try:
            sas_code = sas_file.read_text(encoding="utf-8", errors="replace")
            gold = json.loads(json_file.read_text(encoding="utf-8"))
            py_code = gold.get("python_code") or gold.get("expected_python") or ""
            if not py_code:
                continue
        except Exception:
            continue

        corpus_stats["total_pairs"] += 1
        classes = applicable_classes(sas_code)
        if classes:
            corpus_stats["pairs_with_applicable_classes"] += 1
            report = runner.run_on_code(sas_code, py_code)
            corpus_stats["total_classes_checked"] += report.n_classes_checked
            corpus_stats["total_certificates_issued"] += len(report.certificates)
            corpus_stats["total_failures"] += len(report.failures)
            if report.certificates:
                corpus_stats["pairs_with_certificate"] += 1

    print(f"\n  Total pairs evaluated: {corpus_stats['total_pairs']}")
    print(f"  Pairs with applicable classes: {corpus_stats['pairs_with_applicable_classes']}")
    print(f"  Total classes checked: {corpus_stats['total_classes_checked']}")
    print(f"  Total certificates issued: {corpus_stats['total_certificates_issued']}")
    print(f"  Total failures (FP on gold): {corpus_stats['total_failures']}")
    cert_rate = (
        corpus_stats["pairs_with_certificate"] / corpus_stats["pairs_with_applicable_classes"]
        if corpus_stats["pairs_with_applicable_classes"] > 0
        else 0
    )
    print(f"  Certificate rate: {cert_rate:.1%}")

    results["corpus_stats"] = corpus_stats

    # Compute summary
    n_classes = len(ALL_ERROR_CLASSES)
    cdais_detected = sum(1 for v in results["per_class"].values() if v["cdais_detects_bad"])
    random_detected = sum(1 for v in results["per_class"].values() if v["random_detects_bad"])
    heuristic_detected = sum(1 for v in results["per_class"].values() if v["heuristic_detects_bad"])
    cdais_fp = sum(1 for v in results["per_class"].values() if v["cdais_false_positive"])

    avg_synthesis_ms = (
        np.mean(results["synthesis_times_ms"]) if results["synthesis_times_ms"] else 0
    )
    avg_witness_rows = np.mean([v["witness_rows"] for v in results["per_class"].values()])

    results["summary"] = {
        "cdais_ecdr": f"{cdais_detected}/{n_classes} = {cdais_detected/n_classes:.1%}",
        "random_ecdr": f"{random_detected}/{n_classes} = {random_detected/n_classes:.1%}",
        "heuristic_ecdr": f"{heuristic_detected}/{n_classes} = {heuristic_detected/n_classes:.1%}",
        "cdais_fpr": f"{cdais_fp}/{n_classes} = {cdais_fp/n_classes:.1%}",
        "avg_synthesis_ms": round(avg_synthesis_ms, 1),
        "avg_witness_rows": round(avg_witness_rows, 1),
        "corpus_certificate_rate": f"{cert_rate:.1%}",
    }

    print("\n\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  CDAIS ECDR:      {results['summary']['cdais_ecdr']}")
    print(f"  Random ECDR:     {results['summary']['random_ecdr']}")
    print(f"  Heuristic ECDR:  {results['summary']['heuristic_ecdr']}")
    print(f"  CDAIS FPR:       {results['summary']['cdais_fpr']}")
    print(f"  Avg synthesis:   {avg_synthesis_ms:.1f}ms")
    print(f"  Avg witness:     {avg_witness_rows:.0f} rows")
    print(f"  Cert rate:       {cert_rate:.1%}")

    # Save
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to: {args.output}")


if __name__ == "__main__":
    main()
