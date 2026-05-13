"""Evaluate KB retrieval quality (top-1 / top-k accuracy).

Measures whether the retrieval pipeline returns relevant SAS examples
by using a leave-one-out strategy on the KB itself:
  - For each KB entry, use its SAS code as query
  - Check if entries with the same partition_type appear in top-k results
  - Report top-1 and top-k accuracy, plus mean reciprocal rank (MRR)

Supports comparing base Nomic vs. fine-tuned model.

Usage:
    cd backend
    python scripts/eval/eval_retrieval.py                           # base model
    python scripts/eval/eval_retrieval.py --fine-tuned               # fine-tuned
    python scripts/eval/eval_retrieval.py --compare                  # side-by-side
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import structlog

logger = structlog.get_logger()

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _BACKEND_DIR)

DEFAULT_DB_PATH = os.path.join(_BACKEND_DIR, "data", "lancedb")
FINE_TUNED_PATH = os.path.join(_BACKEND_DIR, "data", "fine_tuned_embedder")
BASE_MODEL = "nomic-ai/nomic-embed-text-v1.5"


def load_kb_entries(db_path: str) -> list[dict]:
    """Load verified KB entries from LanceDB."""
    import lancedb

    db = lancedb.connect(db_path)
    if "sas_python_examples" not in db.table_names():
        print("ERROR: sas_python_examples table not found")
        sys.exit(1)

    table = db.open_table("sas_python_examples")
    df = table.to_pandas()
    df = df[df["verified"] == True]  # noqa: E712

    entries = []
    for _, row in df.iterrows():
        sas = (row.get("sas_code") or "").strip()
        if not sas:
            continue
        entries.append(
            {
                "example_id": row.get("example_id", ""),
                "sas_code": sas,
                "partition_type": row.get("partition_type", "UNKNOWN"),
                "category": row.get("category", ""),
            }
        )
    return entries


def evaluate_retrieval(
    entries: list[dict],
    model_name: str,
    k: int = 5,
    trust_remote_code: bool = True,
) -> dict:
    """Run leave-one-out retrieval evaluation.

    For each entry, embed its SAS code as a query, compute cosine similarity
    against all other entries, and check if same-partition_type entries
    appear in the top-k.
    """
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity

    print(f"\nLoading model: {model_name}")
    model = SentenceTransformer(model_name, trust_remote_code=trust_remote_code)

    print(f"Embedding {len(entries)} KB entries...")
    sas_texts = [f"search_document: {e['sas_code']}" for e in entries]
    embeddings = model.encode(sas_texts, show_progress_bar=True, normalize_embeddings=True)

    query_embeddings = []
    for e in entries:
        q = model.encode(f"search_query: {e['sas_code']}", normalize_embeddings=True)
        query_embeddings.append(q)
    query_embeddings = np.array(query_embeddings)

    sim_matrix = cosine_similarity(query_embeddings, embeddings)

    top_1_correct = 0
    top_k_correct = 0
    reciprocal_ranks = []
    low_similarity_count = 0
    total = len(entries)

    similarity_threshold = 0.55

    for i in range(total):
        scores = sim_matrix[i].copy()
        scores[i] = -1.0  # exclude self

        ranked_indices = np.argsort(scores)[::-1]
        query_type = entries[i]["partition_type"]

        best_score = scores[ranked_indices[0]]
        if best_score < similarity_threshold:
            low_similarity_count += 1

        # Top-1: does the nearest neighbor share partition_type?
        if entries[ranked_indices[0]]["partition_type"] == query_type:
            top_1_correct += 1

        # Top-k: does any of the top-k share partition_type?
        found_rank = None
        for rank, idx in enumerate(ranked_indices[:k]):
            if entries[idx]["partition_type"] == query_type:
                if found_rank is None:
                    found_rank = rank + 1
                if rank == 0 or found_rank is not None:
                    top_k_correct += 1
                    break

        if found_rank is not None:
            reciprocal_ranks.append(1.0 / found_rank)
        else:
            reciprocal_ranks.append(0.0)

    top_1_acc = top_1_correct / total if total > 0 else 0
    top_k_acc = top_k_correct / total if total > 0 else 0
    mrr = float(np.mean(reciprocal_ranks)) if reciprocal_ranks else 0

    return {
        "model": model_name,
        "total_entries": total,
        "k": k,
        "top_1_accuracy": top_1_acc,
        f"top_{k}_accuracy": top_k_acc,
        "mrr": mrr,
        "low_similarity_pct": low_similarity_count / total if total > 0 else 0,
        "similarity_threshold": similarity_threshold,
    }


def print_results(results: dict) -> None:
    """Pretty-print evaluation results."""
    model = results["model"]
    if len(model) > 50:
        model = "..." + model[-47:]

    print(f"\n{'='*60}")
    print(f"  Retrieval Evaluation: {model}")
    print(f"{'='*60}")
    print(f"  KB entries evaluated : {results['total_entries']}")
    print(f"  k                    : {results['k']}")
    print(f"  Top-1 accuracy       : {results['top_1_accuracy']:.1%}")
    k = results["k"]
    top_k_acc = results.get(f"top_{k}_accuracy", 0)
    print(f"  Top-{k} accuracy       : {top_k_acc:.1%}")
    print(f"  MRR                  : {results['mrr']:.4f}")
    print(
        f"  Low-similarity hits  : {results['low_similarity_pct']:.1%} (below {results['similarity_threshold']})"
    )
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate KB retrieval quality")
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--fine-tuned", action="store_true", help="Evaluate fine-tuned model")
    parser.add_argument("--compare", action="store_true", help="Compare base vs fine-tuned")
    parser.add_argument(
        "--model-path",
        default=FINE_TUNED_PATH,
        help="Path to fine-tuned model (default: data/fine_tuned_embedder)",
    )
    args = parser.parse_args()

    entries = load_kb_entries(args.db_path)
    if len(entries) < 5:
        print(f"ERROR: only {len(entries)} KB entries found, need at least 5")
        sys.exit(1)

    print(f"Loaded {len(entries)} verified KB entries")

    if args.compare:
        print("\n--- Base model ---")
        t0 = time.time()
        base_results = evaluate_retrieval(entries, BASE_MODEL, k=args.k)
        base_time = time.time() - t0
        print_results(base_results)

        if not os.path.exists(args.model_path):
            print(f"ERROR: fine-tuned model not found at {args.model_path}")
            print("Run: python scripts/kb/fine_tune_embedder.py first")
            sys.exit(1)

        print("\n--- Fine-tuned model ---")
        t0 = time.time()
        ft_results = evaluate_retrieval(entries, args.model_path, k=args.k)
        ft_time = time.time() - t0
        print_results(ft_results)

        # Delta
        print(f"\n{'='*60}")
        print("  COMPARISON (fine-tuned - base)")
        print(f"{'='*60}")
        delta_1 = ft_results["top_1_accuracy"] - base_results["top_1_accuracy"]
        delta_k = ft_results.get(f"top_{args.k}_accuracy", 0) - base_results.get(
            f"top_{args.k}_accuracy", 0
        )
        delta_mrr = ft_results["mrr"] - base_results["mrr"]
        print(f"  Top-1 accuracy       : {delta_1:+.1%}")
        print(f"  Top-{args.k} accuracy       : {delta_k:+.1%}")
        print(f"  MRR                  : {delta_mrr:+.4f}")
        print(f"  Eval time (base)     : {base_time:.1f}s")
        print(f"  Eval time (fine-tuned): {ft_time:.1f}s")
        print(f"{'='*60}\n")

    elif args.fine_tuned:
        if not os.path.exists(args.model_path):
            print(f"ERROR: fine-tuned model not found at {args.model_path}")
            print("Run: python scripts/kb/fine_tune_embedder.py first")
            sys.exit(1)
        results = evaluate_retrieval(entries, args.model_path, k=args.k)
        print_results(results)

    else:
        results = evaluate_retrieval(entries, BASE_MODEL, k=args.k)
        print_results(results)


if __name__ == "__main__":
    main()
