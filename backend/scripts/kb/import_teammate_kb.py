"""
import_teammate_kb.py — Import 83 SAS→Python pairs from teammate's knowledge_graph.

Source: code-conversion-classic-main/knowledge_graph/atomic/ (EX_01 – EX_83)
Target: our LanceDB sas_python_examples table

Run from backend/:
    venv/Scripts/python scripts/kb/import_teammate_kb.py
    venv/Scripts/python scripts/kb/import_teammate_kb.py --dry-run   # preview only
    venv/Scripts/python scripts/kb/import_teammate_kb.py --stats      # show coverage after import
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

TEAMMATE_KB_PATH = Path(
    r"C:\Users\labou\Downloads\code-conversion-classic-main"
    r"\code-conversion-classic-main\knowledge_graph\atomic"
)

# ── category detection from SAS code ─────────────────────────────────────────

_CATEGORY_RULES: list[tuple[str, str]] = [
    (r"proc\s+univariate", "PROC_UNIVARIATE"),
    (r"proc\s+means", "PROC_MEANS_GROUPBY"),
    (r"proc\s+freq", "PROC_FREQ"),
    (r"proc\s+rank", "PROC_RANK"),
    (r"proc\s+transpose", "PROC_TRANSPOSE"),
    (r"proc\s+sort", "SORT_DIRECTION"),
    (r"proc\s+sql", "LEFT_JOIN"),
    (r"proc\s+export", "PROC_EXPORT"),
    (r"proc\s+import", "PROC_IMPORT"),
    (r"proc\s+print", "PROC_PRINT"),
    (r"proc\s+reg", "STEPWISE_REGRESSION"),
    (r"proc\s+sgplot", "VISUALIZATION"),
    (r"%macro\s+\w+", "MACRO_DEFINITION"),
    (r"\bmerge\b.*\bin=", "MERGE_INDICATOR"),
    (r"\bmerge\b", "MERGE_INDICATOR"),
    (r"\bretain\b", "RETAIN_ACCUMULATOR"),
    (r"\blag\s*\(", "RETAIN_ACCUMULATOR"),
    (r"\bfirst\.\w+|\blast\.\w+", "RETAIN_ACCUMULATOR"),
    (r"\barray\b", "ARRAY_PROCESSING"),
    (r"\bif\b.*\bthen\b", "CONDITIONAL_ASSIGNMENT"),
    (r"\bformat\b", "FORMAT_DISPLAY_ONLY"),
    (r"\bdatalines\b", "DATALINES"),
    (r"\bupdate\b.*\bby\b", "MERGE_INDICATOR"),
    (r"\bcompress\s*\(", "STRING_MANIPULATION"),
    (r"\bsubstr\s*\(", "STRING_MANIPULATION"),
    (r"\binput\b.*\binfile\b", "PROC_IMPORT"),
]


def _detect_category(sas_code: str) -> str:
    s = sas_code.lower()
    for pattern, cat in _CATEGORY_RULES:
        if re.search(pattern, s):
            return cat
    return "DATA_STEP_GENERAL"


def _detect_partition_type(sas_code: str) -> str:
    s = sas_code.lower().strip()
    if re.search(r"proc\s+sql", s):
        return "SQL_BLOCK"
    if s.startswith("proc ") or re.search(r"^\s*proc\s+", s):
        return "PROC_BLOCK"
    if s.startswith("%macro") or re.search(r"%macro\s+\w+", s):
        return "MACRO_DEFINITION"
    return "DATA_STEP"


def _detect_failure_modes(sas_code: str, issues: list[str]) -> str:
    """Extract the most relevant failure mode tag from issues text + SAS code."""
    combined = " ".join(issues).lower() + " " + sas_code.lower()
    checks = [
        ("iterrows", "CONDITIONAL_ASSIGNMENT"),
        ("descending", "SORT_DIRECTION"),
        ("dropna", "PROC_MEANS_OUTPUT"),
        ("groupby", "PROC_MEANS_OUTPUT"),
        ("indicator", "MERGE_SEMANTICS"),
        ("merge", "MERGE_SEMANTICS"),
        ("format", "PROC_FORMAT"),
        ("stepwise", "PROC_REG_STEPWISE"),
        ("compress", "COMPRESS_FUNCTION"),
        ("retain", "RETAIN"),
        ("lag", "RETAIN"),
        ("first\\.", "RETAIN"),
        ("last\\.", "RETAIN"),
        ("left join", "MERGE_SEMANTICS"),
        ("how=.left", "MERGE_SEMANTICS"),
        ("weighted", "PROC_UNIVARIATE"),
        ("univariate", "PROC_UNIVARIATE"),
        ("skewness|kurtosis", "PROC_UNIVARIATE"),
        ("macro", "MACRO_SUBSTITUTION"),
        ("transpose", "PROC_TRANSPOSE"),
    ]
    for pattern, mode in checks:
        if re.search(pattern, combined):
            return mode
    return ""


def _complexity_tier(level: int) -> str:
    return {1: "LOW", 2: "MODERATE", 3: "HIGH"}.get(level, "LOW")


# ── load all JSON files ───────────────────────────────────────────────────────


def load_teammate_pairs() -> list[dict]:
    pairs = []
    files = sorted(TEAMMATE_KB_PATH.glob("EX_*.json"))
    print(f"  Found {len(files)} JSON files in {TEAMMATE_KB_PATH}")

    for fp in files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [!] Skip {fp.name}: {e}")
            continue

        sas_code = (data.get("sas_code") or "").strip()
        python_code = (data.get("python_code") or data.get("python_translation") or "").strip()

        if not sas_code or not python_code:
            print(f"  [!] Skip {fp.name}: missing sas_code or python_code")
            continue

        issues = data.get("issues") or []
        business_logic = data.get("business_logic") or ""
        complexity = int(data.get("complexity") or 1)
        example_id = data.get("example_id") or fp.stem.upper()

        # Build a richer embedding text: business_logic + top issues
        issue_summary = " | ".join(issues[:5]) if issues else ""
        embed_text = f"{business_logic} {issue_summary} {sas_code[:200]}".strip()

        # Store full issues as pipe-separated string for prompt injection
        issues_text = " | ".join(issues) if issues else ""

        pairs.append(
            {
                "example_id": f"TEAMMATE_{example_id}",
                "sas_code": sas_code,
                "python_code": python_code,
                "embed_text": embed_text,
                "partition_type": _detect_partition_type(sas_code),
                "complexity_tier": _complexity_tier(complexity),
                "target_runtime": "python",
                "verified": True,
                "source": "teammate_kg",
                "failure_mode": _detect_failure_modes(sas_code, issues),
                "verification_method": "manual_review",
                "verification_score": 0.88,
                "category": _detect_category(sas_code),
                "version": 1,
                "superseded_by": "",
                "issues_text": issues_text,
            }
        )

    return pairs


# ── main ──────────────────────────────────────────────────────────────────────


def main(args: argparse.Namespace):
    pairs = load_teammate_pairs()
    print(f"\n  Loaded {len(pairs)} valid pairs\n")

    if args.dry_run:
        print("  DRY RUN — category distribution:")
        from collections import Counter

        cats = Counter(p["category"] for p in pairs)
        for cat, n in cats.most_common():
            print(f"    {cat:<35} {n}")
        pts = Counter(p["partition_type"] for p in pairs)
        print("\n  partition_type distribution:")
        for pt, n in pts.most_common():
            print(f"    {pt:<35} {n}")
        return

    print("  Loading NomicEmbedder (768-dim, CPU)...")
    from partition.kb.kb_writer import KBWriter
    from partition.raptor.embedder import NomicEmbedder

    embedder = NomicEmbedder()
    writer = KBWriter()

    print(f"  Embedding {len(pairs)} pairs...")
    inserted = 0
    skipped = 0

    for i, p in enumerate(pairs, 1):
        label = f"  [{i:02d}/{len(pairs)}] {p['category']:<30} {p['partition_type']}"
        try:
            embed_text = p.pop("embed_text")
            embedding = embedder.embed(embed_text)
            # embed() may return ndarray or list depending on version
            emb_list = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

            writer.insert_pairs(
                [
                    {
                        **p,
                        "embedding": emb_list,
                        "created_at": __import__("datetime").datetime.utcnow().isoformat(),
                    }
                ]
            )
            print(f"{label}  OK")
            inserted += 1
        except Exception as e:
            print(f"{label}  FAIL  {e}")
            skipped += 1

    print(f"\n  Inserted {inserted} pairs  ({skipped} skipped)")

    if args.stats or inserted > 0:
        show_stats(writer)


def show_stats(writer=None):
    import lancedb

    _HERE = os.path.dirname(os.path.abspath(__file__))
    _BACKEND = os.path.abspath(os.path.join(_HERE, "..", ".."))
    db_path = os.path.join(_BACKEND, "data", "lancedb")

    db = lancedb.connect(db_path)
    tables_result = db.list_tables()
    tables_list = tables_result.tables if hasattr(tables_result, "tables") else list(tables_result)
    if "sas_python_examples" not in tables_list:
        print("  [!] Table not found.")
        return

    t = db.open_table("sas_python_examples")
    df = t.to_pandas()
    print(f"\n  Total pairs in KB: {len(df)}")

    print("\n  By source:")
    for src, n in df["source"].value_counts().items():
        print(f"    {src:<30} {n}")

    print("\n  By category:")
    for cat, n in df["category"].value_counts().items():
        print(f"    {cat:<35} {n}")

    print("\n  By partition_type:")
    for pt, n in df["partition_type"].value_counts().items():
        print(f"    {pt:<35} {n}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    parser.add_argument("--stats", action="store_true", help="Show KB stats after import")
    main(parser.parse_args())
