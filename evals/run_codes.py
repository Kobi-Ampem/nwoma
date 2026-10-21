"""Evaluate LOINC mapping: top-1 accuracy and top-5 recall, with an ablation of each part.

uv run python -m evals.run_codes

Queries are the result rows of every test and unseen-layout document: the name and unit as
printed. The truth is the code that fits the printed unit (`LabTest.code_for`). Scored per row
(how often a real report is right) and per unique query (how many distinct spellings work).
"""

import argparse
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from datagen.catalogue import BY_CODE
from datagen.models import LabReport
from evals.run_llm import sample_docs
from normalise.embed import Embedder
from normalise.loinc import LoincMapper

Query = tuple[str, str | None, str]  # name, unit, language


def queries(labels: Path) -> tuple[Counter[Query], dict[Query, str]]:
    docs = sample_docs(labels, ["test", "test_unseen"], 10**6, 0)
    counts: Counter[Query] = Counter()
    gold: dict[Query, str] = {}
    for doc in docs:
        if not isinstance(doc.report, LabReport):
            continue  # referral diagnoses are mapped to ICD-10, scored separately
        for row in doc.report.results:
            q = (row.name.text, row.unit.text if row.unit else None, doc.lang)
            counts[q] += 1
            gold[q] = BY_CODE[row.name.value].code_for(doc.lang)
    return counts, gold


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=Path("data/docs/labels.jsonl"))
    parser.add_argument("--loinc", type=Path, default=Path("data/loinc"))
    parser.add_argument("--out", type=Path, default=Path("evals/results/codes_loinc.json"))
    args = parser.parse_args()

    counts, gold = queries(args.labels)
    mapper = LoincMapper(args.loinc, Embedder().encode, Path("data/cache/loinc_names.npy"))
    index = mapper.index
    print(f"search space: {len(index.codes)} codes, {len(index.names)} names")
    print(f"queries: {sum(counts.values())} rows, {len(counts)} unique (name, unit, language)")

    def ranked(codes: list[int]) -> list[str]:
        return [index.codes[c] for c in codes[:5]]

    systems: dict[str, Callable[[Query], list[str]]] = {
        "keyword (BM25 trigrams)": lambda q: ranked(index.keyword(q[0])),
        "semantic (E5 embeddings)": lambda q: ranked(index.semantic(q[0])),
        "hybrid (RRF)": lambda q: [h.code for h in index.search(q[0])],
        "+ unit and specimen": lambda q: [h.code for h in mapper.map(q[0], q[1], prior=0)],
        "+ popularity prior": lambda q: [h.code for h in mapper.map(q[0], q[1])],
    }

    def same_test(a: str, b: str) -> bool:
        """Same substance, property and specimen; the method may differ."""
        ra, rb = mapper.rows[a], mapper.rows[b]
        return all(ra[f] == rb[f] for f in ("COMPONENT", "PROPERTY", "SYSTEM"))

    report: dict[str, object] = {}
    misses: list[tuple[str, str | None, str, str, list[str]]] = []
    for name, system in systems.items():
        top1 = top5 = u1 = u5 = same1 = 0
        for q, n in counts.items():
            got = system(q)
            hit1, hit5 = bool(got) and got[0] == gold[q], gold[q] in got
            top1 += n * hit1
            top5 += n * hit5
            same1 += n * (bool(got) and same_test(got[0], gold[q]))
            u1 += hit1
            u5 += hit5
            if name == "+ popularity prior" and not hit1:
                misses.append((*q, gold[q], got[:3]))
        rows, uniq = sum(counts.values()), len(counts)
        report[name] = {
            "rows_top1": top1 / rows,
            "rows_top5": top5 / rows,
            "unique_top1": u1 / uniq,
            "unique_top5": u5 / uniq,
            "rows_top1_same_test": same1 / rows,
        }
        print(
            f"{name:25} rows: top-1 {top1 / rows:6.1%}  top-5 {top5 / rows:6.1%}   "
            f"unique: top-1 {u1 / uniq:6.1%}  top-5 {u5 / uniq:6.1%}   "
            f"same test: {same1 / rows:6.1%}"
        )
    print(f"\nfull mapper misses ({len(misses)} unique):")
    for m in sorted(misses, key=lambda m: -counts[m[:3]])[:15]:
        print(f"  {counts[m[:3]]:4}x {m[0]!r:32} {m[1]!s:10} {m[2]}  want {m[3]}  got {m[4]}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
