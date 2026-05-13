"""Fine-tune the Nomic embedder on SAS→Python KB pairs.

Adapts the approach from the supervisor's Script_similarity_check.py
(CosineSimilarityLoss on domain-specific pairs) to Codara's LanceDB KB.

Generates contrastive training data automatically:
  - Positive pairs (score ~1.0): SAS blocks with same partition_type
  - Medium pairs  (score ~0.5): same broad category, different partition_type
  - Negative pairs (score ~0.0): completely different partition_type + category

Usage:
    cd backend
    python scripts/kb/fine_tune_embedder.py                          # defaults
    python scripts/kb/fine_tune_embedder.py --epochs 10 --batch 16   # custom
    python scripts/kb/fine_tune_embedder.py --eval-only              # just evaluate
"""

from __future__ import annotations

import argparse
import itertools
import os
import random
import sys

import numpy as np
import structlog

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BACKEND_DIR)

DEFAULT_DB_PATH = os.path.join(_BACKEND_DIR, "data", "lancedb")
DEFAULT_OUTPUT_DIR = os.path.join(_BACKEND_DIR, "data", "fine_tuned_embedder")
BASE_MODEL = "nomic-ai/nomic-embed-text-v1.5"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_kb_pairs(db_path: str) -> list[dict]:
    """Load all verified SAS→Python pairs from LanceDB."""
    import lancedb

    db = lancedb.connect(db_path)
    if "sas_python_examples" not in db.table_names():
        logger.error("kb_table_missing", path=db_path)
        sys.exit(1)

    table = db.open_table("sas_python_examples")
    df = table.to_pandas()
    df = df[df["verified"] == True]  # noqa: E712

    pairs = []
    for _, row in df.iterrows():
        sas = (row.get("sas_code") or "").strip()
        py = (row.get("python_code") or "").strip()
        ptype = row.get("partition_type", "UNKNOWN")
        cat = row.get("category", "")
        if sas and py:
            pairs.append(
                {
                    "sas_code": sas,
                    "python_code": py,
                    "partition_type": ptype,
                    "category": cat,
                }
            )

    logger.info("kb_pairs_loaded", count=len(pairs))
    return pairs


# ---------------------------------------------------------------------------
# Contrastive pair generation
# ---------------------------------------------------------------------------

_BROAD_CATEGORY = {
    "DATA_STEP_BASIC": "data_step",
    "DATA_STEP_ADVANCED": "data_step",
    "PROC_SQL": "sql",
    "PROC_SORT": "proc",
    "PROC_MEANS": "proc",
    "PROC_FREQ": "proc",
    "PROC_TRANSPOSE": "proc",
    "PROC_REPORT": "proc",
    "PROC_PRINT": "proc",
    "MACRO_DEF": "macro",
    "MACRO_CALL": "macro",
    "GLOBAL_STATEMENT": "global",
}


def _broad(ptype: str) -> str:
    return _BROAD_CATEGORY.get(ptype, ptype.lower())


def generate_training_pairs(
    kb_pairs: list[dict],
    max_positives: int = 2000,
    max_negatives: int = 2000,
    seed: int = 42,
) -> list[tuple[str, str, float]]:
    """Generate (text_a, text_b, similarity_score) triples for fine-tuning.

    Strategy:
      1. Positive (1.0): SAS_i ↔ SAS_j where partition_type matches
      2. Medium  (0.5): same broad category, different partition_type
      3. Negative (0.0): different broad category entirely
      4. Cross-modal positive (0.8): SAS_i ↔ Python_i (own translation)
    """
    rng = random.Random(seed)
    triples: list[tuple[str, str, float]] = []

    by_type: dict[str, list[dict]] = {}
    for p in kb_pairs:
        by_type.setdefault(p["partition_type"], []).append(p)

    by_broad: dict[str, list[dict]] = {}
    for p in kb_pairs:
        by_broad.setdefault(_broad(p["partition_type"]), []).append(p)

    # 1. Positive pairs — same partition_type
    positives = []
    for ptype, items in by_type.items():
        if len(items) < 2:
            continue
        for a, b in itertools.combinations(items, 2):
            positives.append((a["sas_code"], b["sas_code"], 1.0))
    rng.shuffle(positives)
    triples.extend(positives[:max_positives])

    # 2. Cross-modal positive — SAS ↔ own Python translation
    cross_modal = [(p["sas_code"], p["python_code"], 0.8) for p in kb_pairs]
    rng.shuffle(cross_modal)
    triples.extend(cross_modal[: max_positives // 2])

    # 3. Medium pairs — same broad category, different partition_type
    mediums = []
    for broad, items in by_broad.items():
        types_in_broad = set(p["partition_type"] for p in items)
        if len(types_in_broad) < 2:
            continue
        for a, b in itertools.combinations(items, 2):
            if a["partition_type"] != b["partition_type"]:
                mediums.append((a["sas_code"], b["sas_code"], 0.5))
    rng.shuffle(mediums)
    triples.extend(mediums[: max_positives // 2])

    # 4. Negative pairs — different broad category
    broad_keys = list(by_broad.keys())
    negatives = []
    attempts = 0
    while len(negatives) < max_negatives and attempts < max_negatives * 10:
        attempts += 1
        b1, b2 = rng.sample(broad_keys, 2) if len(broad_keys) >= 2 else (broad_keys[0], broad_keys[0])
        if b1 == b2:
            continue
        a = rng.choice(by_broad[b1])
        b = rng.choice(by_broad[b2])
        negatives.append((a["sas_code"], b["sas_code"], 0.0))
    triples.extend(negatives)

    rng.shuffle(triples)
    logger.info(
        "training_pairs_generated",
        total=len(triples),
        positives=len(positives[:max_positives]),
        cross_modal=len(cross_modal[: max_positives // 2]),
        mediums=len(mediums[: max_positives // 2]),
        negatives=len(negatives),
    )
    return triples


# ---------------------------------------------------------------------------
# Fine-tuning
# ---------------------------------------------------------------------------


def fine_tune(
    triples: list[tuple[str, str, float]],
    model_name: str = BASE_MODEL,
    output_path: str = DEFAULT_OUTPUT_DIR,
    epochs: int = 5,
    batch_size: int = 32,
    lr: float = 1e-5,
    dev_fraction: float = 0.1,
) -> None:
    """Fine-tune a SentenceTransformer on contrastive SAS pairs."""
    from sentence_transformers import SentenceTransformer, InputExample, losses
    from sentence_transformers.evaluation import EmbeddingSimilarityEvaluator
    from torch.utils.data import DataLoader

    logger.info(
        "fine_tune_start",
        model=model_name,
        output=output_path,
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        n_triples=len(triples),
    )

    model = SentenceTransformer(model_name, trust_remote_code=True)

    # Split train / dev
    split_idx = max(1, int(len(triples) * (1 - dev_fraction)))
    train_triples = triples[:split_idx]
    dev_triples = triples[split_idx:]

    train_examples = [
        InputExample(texts=[a, b], label=np.float32(score))
        for a, b, score in train_triples
    ]
    dev_examples = [
        InputExample(texts=[a, b], label=np.float32(score))
        for a, b, score in dev_triples
    ]

    train_loader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)
    loss = losses.CosineSimilarityLoss(model=model)

    evaluator = EmbeddingSimilarityEvaluator.from_input_examples(
        dev_examples, batch_size=batch_size * 2
    )

    os.makedirs(output_path, exist_ok=True)

    model.fit(
        train_objectives=[(train_loader, loss)],
        epochs=epochs,
        evaluator=evaluator,
        scheduler="constantlr",
        optimizer_params={"lr": lr},
        output_path=output_path,
        show_progress_bar=True,
    )

    logger.info("fine_tune_complete", output=output_path)
    print(f"\nFine-tuned model saved to: {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune Nomic embedder on KB pairs")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="LanceDB path")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DIR, help="Output model dir")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-5)
    parser.add_argument("--max-positives", type=int, default=2000)
    parser.add_argument("--max-negatives", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="Only evaluate retrieval (no training). Use scripts/eval/eval_retrieval.py instead.",
    )
    args = parser.parse_args()

    if args.eval_only:
        print("Use: python scripts/eval/eval_retrieval.py --db-path", args.db_path)
        sys.exit(0)

    kb_pairs = load_kb_pairs(args.db_path)
    if len(kb_pairs) < 10:
        logger.error("too_few_kb_pairs", count=len(kb_pairs), min_required=10)
        sys.exit(1)

    triples = generate_training_pairs(
        kb_pairs,
        max_positives=args.max_positives,
        max_negatives=args.max_negatives,
        seed=args.seed,
    )

    fine_tune(
        triples,
        output_path=args.output,
        epochs=args.epochs,
        batch_size=args.batch,
        lr=args.lr,
    )


if __name__ == "__main__":
    main()
