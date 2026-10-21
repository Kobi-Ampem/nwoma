"""Evaluate the int8 ONNX NER model on the same fixed sample as the LLM baseline.

uv run python -m evals.run_ner --model-dir models/ner

Same documents (seed 42), same scorer, same report as `evals.run_llm`, so the two are comparable.
Latency is measured one document at a time on one CPU thread, the way the API will run it.
"""

import argparse
import json
import time
from pathlib import Path

from evals.run_llm import _print, report, sample_docs
from extract.llm import LLMResult
from extract.ner import NerExtractor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/docs/labels.jsonl"))
    parser.add_argument("--splits", nargs="+", default=["test", "test_unseen"])
    parser.add_argument("--per-split", type=int, default=100)
    parser.add_argument("--per-split-referral", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model-dir", type=Path, default=Path("models/ner"))
    parser.add_argument("--out", type=Path, default=Path("evals/results"))
    args = parser.parse_args()

    docs = sample_docs(args.labels, args.splits, args.per_split, args.seed, args.per_split_referral)
    extractor = NerExtractor.from_onnx(args.model_dir)
    extractor.extract(docs[0].text)  # warm-up: the first call loads and optimises the graph
    results: dict[str, LLMResult] = {}
    for doc in docs:
        start = time.perf_counter()
        extraction = extractor.extract(doc.text)
        results[doc.doc_id] = LLMResult(extraction, 0, 0, time.perf_counter() - start, False)

    rep = report(docs, results, None)
    rep |= {"model": "xlm-roberta-base int8 ONNX", "sample": len(docs), "seed": args.seed}
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "ner_xlmr_int8.json"
    path.write_text(json.dumps(rep, indent=2) + "\n")
    _print(rep)
    print(f"\nsaved {path}")


if __name__ == "__main__":
    main()
