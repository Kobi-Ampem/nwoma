"""Evaluate the cascade: NER first, Gemini only when the validator objects.

uv run python -m evals.run_cascade

Same 500-document sample as the extractor baselines. Gemini answers come from the cache, so this
spends no quota. Compared: NER only, Gemini only, the cascade, and perfect routing (send exactly
the documents NER got wrong), the ceiling for any router.
"""

import argparse
import json
import statistics
import time
from collections import Counter
from pathlib import Path

from datagen.models import LabeledDoc
from evals.run_llm import sample_docs
from evals.score import all_correct, prf, score_doc
from extract.cascade import Cascade
from extract.llm import GeminiExtractor
from extract.ner import NerExtractor
from extract.schema import Extraction
from extract.validate import validate


def _summary(docs: list[LabeledDoc], picks: dict[str, Extraction]) -> dict[str, float]:
    total: Counter[str] = Counter()
    correct = 0
    for doc in docs:
        counts = score_doc(doc, picks[doc.doc_id])
        total += counts
        correct += all_correct(counts)
    p, r, f1 = prf(total)
    return {"precision": p, "recall": r, "f1": f1, "doc_all_correct": correct / len(docs)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/docs/labels.jsonl"))
    parser.add_argument("--model-dir", type=Path, default=Path("models/ner"))
    parser.add_argument("--gemini-model", default="gemini-3.5-flash-lite")
    parser.add_argument("--out", type=Path, default=Path("evals/results/cascade.json"))
    args = parser.parse_args()

    docs = sample_docs(args.labels, ["test", "test_unseen"], 150, 42, 100)
    ner = NerExtractor.from_onnx(args.model_dir)
    gemini = GeminiExtractor(args.gemini_model, Path("data/llm_cache"), client=object())  # type: ignore[arg-type]

    # The cascade is evaluated by running production code, Cascade.run(): it detects the
    # document type itself and applies the same routing and validity rules. Gemini answers come
    # from the cache; a cache miss raises, which the cascade treats as an LLM failure.
    cascade = Cascade(ner, gemini)
    ner_out: dict[str, Extraction] = {}
    ner_ms: dict[str, float] = {}
    gem_out: dict[str, Extraction] = {}
    gem_s: dict[str, float] = {}
    casc_out: dict[str, Extraction] = {}
    casc_llm: set[str] = set()
    type_errors = 0
    for doc in docs:
        start = time.perf_counter()
        ner_out[doc.doc_id] = ner.extract(doc.text)
        ner_ms[doc.doc_id] = 1000 * (time.perf_counter() - start)
        cached = gemini.extract(doc.doc_id, doc.text)  # cache only: the client is a dummy
        gem_out[doc.doc_id], gem_s[doc.doc_id] = cached.extraction, cached.latency_s
        result = cascade.run(doc.doc_id, doc.text)
        casc_out[doc.doc_id] = result.extraction
        if result.source == "llm":
            casc_llm.add(doc.doc_id)
        type_errors += result.doc_type != doc.report.doc_type

    ner_right = {d.doc_id: all_correct(score_doc(d, ner_out[d.doc_id])) for d in docs}
    systems = {
        "NER only": ner_out,
        "Gemini only": gem_out,
        "cascade (validator routes)": casc_out,
        "perfect routing (ceiling)": {
            d.doc_id: ner_out[d.doc_id] if ner_right[d.doc_id] else gem_out[d.doc_id] for d in docs
        },
    }
    routed = {
        "NER only": set(),
        "Gemini only": {d.doc_id for d in docs},
        "cascade (validator routes)": casc_llm,
        "perfect routing (ceiling)": {d.doc_id for d in docs if not ner_right[d.doc_id]},
    }
    report: dict[str, object] = {}
    print(f"{'system':28} {'F1':>6} {'all-correct':>11} {'to Gemini':>9} {'mean s/doc':>10}")
    for name, picks in systems.items():
        s = _summary(docs, picks)
        latency = statistics.mean(
            ner_ms[d.doc_id] / 1000 * (name != "Gemini only")
            + gem_s[d.doc_id] * (d.doc_id in routed[name])
            for d in docs
        )
        s |= {"share_to_gemini": len(routed[name]) / len(docs), "mean_seconds_per_doc": latency}
        report[name] = s
        print(
            f"{name:28} {s['f1']:6.3f} {s['doc_all_correct']:11.1%} "
            f"{s['share_to_gemini']:9.1%} {latency:10.2f}"
        )

    flagged = {d.doc_id: bool(validate(ner_out[d.doc_id], d.report.doc_type)) for d in docs}
    wrong = {d.doc_id for d in docs if not ner_right[d.doc_id]}
    caught = {d for d in wrong if flagged[d]}
    false_alarms = {d.doc_id for d in docs if flagged[d.doc_id]} - wrong
    report["validator_on_ner"] = {
        "ner_docs_wrong": len(wrong),
        "caught": len(caught),
        "false_alarms": len(false_alarms),
        "catch_rate": len(caught) / len(wrong) if wrong else 0.0,
    }
    print(
        f"\nvalidator on NER output: {len(wrong)} documents wrong, {len(caught)} caught "
        f"({len(caught) / len(wrong):.0%}); {len(false_alarms)} flagged that were right"
    )
    still = sum(
        bool(validate(systems["cascade (validator routes)"][d.doc_id], d.report.doc_type))
        for d in docs
    )
    report["cascade_needs_review"] = still / len(docs)
    report["doc_type_errors"] = type_errors
    print(f"document type misdetected by the cascade: {type_errors} of {len(docs)}")
    print(f"after the cascade, {still} documents ({still / len(docs):.1%}) still raise an issue")
    args.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
