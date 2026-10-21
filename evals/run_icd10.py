"""Evaluate ICD-10-CM mapping of diagnoses as letters print them, in English and French.

uv run python -m evals.run_icd10

Queries are every diagnosis wording the referral catalogue can print; the truth is its code.
Reported per language: exact top-1 and top-5, and the same 3-character category (E11 for any
type 2 diabetes code), with each part of the mapper switched on in turn.
"""

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from datagen.referral_catalogue import CONDITIONS
from normalise.embed import Embedder
from normalise.icd10 import Icd10Mapper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--icd10", type=Path, default=Path("data/icd10cm/Code Descriptions/icd10cm_order_2027.txt")
    )
    parser.add_argument("--out", type=Path, default=Path("evals/results/codes_icd10.json"))
    args = parser.parse_args()

    mapper = Icd10Mapper(args.icd10, Embedder().encode, Path("data/cache/icd10_names.npy"))
    index = mapper.index
    print(f"search space: {len(index.codes)} billable codes, {len(index.names)} descriptions")
    report: dict[str, dict[str, dict[str, float]]] = {}
    for lang in ("en", "fr"):
        queries = [
            (name, c.icd10)
            for c in CONDITIONS.values()
            for name in (c.names_fr if lang == "fr" else c.names_en)
        ]
        systems: dict[str, Callable[[str], list[str]]] = {
            "keyword": lambda q: [index.codes[i] for i in index.keyword(q)[:5]],
            "semantic": lambda q: [index.codes[i] for i in index.semantic(q)[:5]],
            "hybrid": lambda q: [h.code for h in mapper.map(q, guidelines=False)],
            "hybrid + coding guidelines": lambda q: [h.code for h in mapper.map(q)],
        }
        report[lang] = {}
        for name, system in systems.items():
            got = [(system(q), gold) for q, gold in queries]
            n = len(got)
            scores = {
                "top1": sum(g[:1] == [gold] for g, gold in got) / n,
                "top5": sum(gold in g for g, gold in got) / n,
                "same_category": sum(bool(g) and g[0][:3] == gold[:3] for g, gold in got) / n,
            }
            report[lang][name] = scores
            print(
                f"{lang} {name:27} top-1 {scores['top1']:6.1%}  top-5 {scores['top5']:6.1%}  "
                f"same category {scores['same_category']:6.1%}  (n={n})"
            )
    args.out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
