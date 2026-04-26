import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from uuid import uuid4

from partition.chunking.boundary_detector import BoundaryDetector, BoundaryDetectorAgent
from partition.models.file_metadata import FileMetadata
from partition.streaming.pipeline import run_streaming_pipeline


def _make_file_meta(sas_path):
    raw = sas_path.read_bytes()
    enc = "utf-8"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        enc = "latin-1"
    return FileMetadata(
        file_id=uuid4(),
        file_path=str(sas_path),
        encoding=enc,
        content_hash=hashlib.sha256(raw).hexdigest(),
        file_size_bytes=len(raw),
        line_count=raw.count(b"\n") + 1,
        lark_valid=True,
    )


def evaluate_boundary_accuracy(results, gold_dir, line_tolerance=2):
    total_gold = 0
    correct = 0
    missed = []
    type_confusion = {}
    per_file = {}
    for gf in sorted(Path(gold_dir).glob("*.gold.json")):
        with open(gf, encoding="utf-8") as f:
            gold = json.load(f)
        stem = Path(gold["file_path"]).stem
        file_events = results.get(stem, [])
        gold_blocks = gold.get("blocks", [])
        fc = 0
        for gb in gold_blocks:
            total_gold += 1
            matched = False
            for ev in file_events:
                if (
                    ev.partition_type.value == gb["partition_type"]
                    and abs(ev.line_start - gb["line_start"]) <= line_tolerance
                    and abs(ev.line_end - gb["line_end"]) <= line_tolerance
                ):
                    correct += 1
                    fc += 1
                    matched = True
                    break
            if not matched:
                missed.append(
                    {
                        "file": stem,
                        "gold_type": gb["partition_type"],
                        "gold_start": gb["line_start"],
                        "gold_end": gb["line_end"],
                    }
                )
                cl = min(
                    file_events, key=lambda e: abs(e.line_start - gb["line_start"]), default=None
                )
                if cl:
                    k = (cl.partition_type.value, gb["partition_type"])
                    type_confusion[k] = type_confusion.get(k, 0) + 1
        per_file[stem] = {"detected": len(file_events), "gold": len(gold_blocks), "correct": fc}
    acc = correct / total_gold if total_gold > 0 else 0.0
    return {
        "accuracy": round(acc, 4),
        "correct": correct,
        "total": total_gold,
        "target": 0.80,
        "passed": acc >= 0.80,
        "missed": missed,
        "confusion": {str(k): v for k, v in type_confusion.items()},
        "per_file": per_file,
    }


async def _run_corpus(gold_dir, enable_llm):
    results = {}
    sas_files = sorted(Path(gold_dir).glob("*.sas"))
    print(f"Processing {len(sas_files)} SAS file(s)...\n")
    for sf in sas_files:
        try:
            fm = _make_file_meta(sf)
            pairs = await run_streaming_pipeline(fm)
            if enable_llm:
                agent = BoundaryDetectorAgent(trace_id=uuid4())
                events = await agent.process(pairs, fm.file_id)
            else:
                events = BoundaryDetector().detect(pairs, fm.file_id)
            results[sf.stem] = events
            print(f"  {sf.name:<50} {len(events):>3} block(s)")
        except Exception as exc:
            print(f"  [WARN] {sf.name}: {exc}")
            results[sf.stem] = []
    return results


async def main():
    parser = argparse.ArgumentParser(description="SAS boundary detection benchmark")
    parser.add_argument("--gold", default="knowledge_base/gold_standard")
    parser.add_argument("--tolerance", type=int, default=2)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Enable Groq LLM for ambiguous blocks (needs GROQ_API_KEY)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    gold_dir = Path(args.gold)
    if not gold_dir.exists():
        print(f"[ERROR] Not found: {gold_dir}")
        raise SystemExit(1)
    if args.llm:
        import os

        if not os.environ.get("GROQ_API_KEY"):
            print("[ERROR] --llm needs GROQ_API_KEY")
            raise SystemExit(1)
        print("LLM mode: Groq (llama-3.1-8b-instant)\n")
    else:
        print("Deterministic mode (rule-based only, no LLM calls)\n")
    results = await _run_corpus(gold_dir, enable_llm=args.llm)
    report = evaluate_boundary_accuracy(results, gold_dir, args.tolerance)
    sep = "-" * 52
    print(f"\n{sep}")
    print(f"  Accuracy : {report['accuracy']:.1%}  (target >= 80%)")
    print(f"  Correct  : {report['correct']} / {report['total']}")
    print(f"  Status   : {'PASSED' if report['passed'] else 'FAILED'}")
    print(f"{sep}\n")
    if args.verbose:
        print("-- Per-file breakdown --")
        for stem, info in sorted(report["per_file"].items()):
            pct = info["correct"] / info["gold"] * 100 if info["gold"] else 0
            ok = "OK" if info["correct"] == info["gold"] else "!!"
            print(f"  {ok} {stem:<44} {info['correct']}/{info['gold']}  ({pct:.0f}%)")
        if report["confusion"]:
            print("\n-- Confusion (predicted -> gold) --")
            for ps, cnt in sorted(report["confusion"].items(), key=lambda x: -x[1]):
                print(f"  {ps}  ({cnt}x)")
        if report["missed"]:
            print("\n-- Missed blocks --")
            for m in report["missed"][:20]:
                print(f"  {m['file']}: {m['gold_type']} L{m['gold_start']}-{m['gold_end']}")
            if len(report["missed"]) > 20:
                print(f"  ... and {len(report['missed']) - 20} more")


if __name__ == "__main__":
    asyncio.run(main())
