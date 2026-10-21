"""Evaluate the Gemini extractor on a fixed sample of held-out documents.

uv run python -m evals.run_llm --per-split 100

The sample is fixed by seed, so reruns score the same documents and are served from the cache.
If the daily quota runs out, the run stops, scores what it has, and resumes from the cache later.
"""

import argparse
import json
import os
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv

from datagen.layouts import LAYOUTS
from datagen.models import LabeledDoc
from evals.score import HEADER, ROW, all_correct, prf, score_doc
from extract.llm import GeminiExtractor, LLMResult, QuotaExhausted


def sample_docs(path: Path, splits: list[str], per_split: int, seed: int) -> list[LabeledDoc]:
    by_split: dict[str, list[LabeledDoc]] = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for line in f:
            doc = LabeledDoc.model_validate_json(line)
            if doc.split in splits:
                by_split[doc.split].append(doc)
    rng = random.Random(seed)
    chosen: list[LabeledDoc] = []
    for split in splits:
        docs = sorted(by_split[split], key=lambda d: d.doc_id)
        chosen += rng.sample(docs, min(per_split, len(docs)))
    return chosen


def _slice_report(counts: Counter[str], correct: int, n: int) -> dict[str, float]:
    p, r, f1 = prf(counts)
    return {"docs": n, "precision": p, "recall": r, "f1": f1, "doc_all_correct": correct / n}


def report(
    docs: list[LabeledDoc], results: dict[str, LLMResult], prices: tuple[float, float] | None
) -> dict[str, object]:
    total: Counter[str] = Counter()
    slices: dict[str, Counter[str]] = defaultdict(Counter)
    slice_correct: Counter[str] = Counter()
    slice_n: Counter[str] = Counter()
    for doc in docs:
        if doc.doc_id not in results:
            continue
        counts = score_doc(doc, results[doc.doc_id].extraction)
        total += counts
        # Skeleton separates the fresh held-out layouts (ledger) from ones already examined (list).
        skeleton = f"skeleton={LAYOUTS[doc.template].skeleton}"
        for key in (
            "all",
            f"split={doc.split}",
            f"lang={doc.lang}",
            f"source={doc.source}",
            skeleton,
        ):
            slices[key] += counts
            slice_n[key] += 1
            slice_correct[key] += all_correct(counts)
    done = list(results.values())
    latencies = sorted(r.latency_s for r in done)
    tokens_in = statistics.mean(r.input_tokens for r in done)
    tokens_out = statistics.mean(r.output_tokens for r in done)
    out: dict[str, object] = {
        "docs_scored": len(done),
        "schema_failures": sum(not r.valid for r in done),
        "by_label": {
            label: dict(zip(("precision", "recall", "f1"), prf(total, [label]), strict=True))
            for label in HEADER + ROW
        },
        "slices": {k: _slice_report(slices[k], slice_correct[k], slice_n[k]) for k in slices},
        "latency_s": {
            "p50": latencies[len(latencies) // 2],
            "p95": latencies[int(len(latencies) * 0.95)],
        },
        "tokens_per_doc": {"input": tokens_in, "output": tokens_out},
    }
    if prices:
        out["usd_per_1000_docs"] = (tokens_in * prices[0] + tokens_out * prices[1]) / 1000
    return out


def _print(rep: dict[str, object]) -> None:
    print(f"\ndocs scored: {rep['docs_scored']}  schema failures: {rep['schema_failures']}")
    print(f"\n{'slice':22} {'docs':>5} {'P':>6} {'R':>6} {'F1':>6} {'all-correct':>11}")
    for name, s in sorted(rep["slices"].items()):  # type: ignore[attr-defined]
        print(
            f"{name:22} {s['docs']:>5} {s['precision']:6.3f} {s['recall']:6.3f} "
            f"{s['f1']:6.3f} {s['doc_all_correct']:11.1%}"
        )
    print(f"\n{'field':16} {'P':>6} {'R':>6} {'F1':>6}")
    for label, m in rep["by_label"].items():  # type: ignore[attr-defined]
        print(f"{label:16} {m['precision']:6.3f} {m['recall']:6.3f} {m['f1']:6.3f}")
    print(f"\nlatency {rep['latency_s']}  tokens/doc {rep['tokens_per_doc']}")
    if "usd_per_1000_docs" in rep:
        print(f"cost at paid prices: ${rep['usd_per_1000_docs']:.2f} per 1,000 documents")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/docs/labels.jsonl"))
    parser.add_argument("--splits", nargs="+", default=["test", "test_unseen"])
    parser.add_argument("--per-split", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    parser.add_argument("--rpm", type=float, default=10, help="requests per minute to stay under")
    parser.add_argument("--thinking", default=None, help="thinking level, e.g. low")
    parser.add_argument("--price-in", type=float, help="USD per 1M input tokens (paid tier)")
    parser.add_argument("--price-out", type=float, help="USD per 1M output tokens (paid tier)")
    parser.add_argument("--cache", type=Path, default=Path("data/llm_cache"))
    parser.add_argument("--out", type=Path, default=Path("evals/results"))
    args = parser.parse_args()

    docs = sample_docs(args.labels, args.splits, args.per_split, args.seed)
    extractor = GeminiExtractor(args.model, args.cache, None, 60 / args.rpm, args.thinking)
    results: dict[str, LLMResult] = {}
    stopped = False
    for i, doc in enumerate(docs, 1):
        try:
            results[doc.doc_id] = extractor.extract(doc.doc_id, doc.text)
        except QuotaExhausted:
            print(f"\nDaily quota reached after {len(results)}/{len(docs)} docs; rerun tomorrow.")
            stopped = True
            break
        if not results[doc.doc_id].cached:
            print(f"{i}/{len(docs)} {doc.doc_id}", file=sys.stderr)
    if not results:
        sys.exit("Nothing extracted yet.")

    prices = (args.price_in, args.price_out) if args.price_in and args.price_out else None
    rep = report(docs, results, prices)
    rep |= {"model": args.model, "complete": not stopped, "sample": len(docs), "seed": args.seed}
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"llm_{args.model}.json"
    path.write_text(json.dumps(rep, indent=2) + "\n")
    _print(rep)
    print(f"\nsaved {path}")


if __name__ == "__main__":
    main()
