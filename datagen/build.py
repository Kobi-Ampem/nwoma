"""Generate labelled synthetic lab reports from Synthea output.

uv run python -m datagen.build --n 50 --seed 42
"""

import argparse
import random
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from faker import Faker

from datagen.compose import compose_report
from datagen.models import LabeledDoc, Lang, SourceLabVisit
from datagen.render import extract_text, locate_spans, render_pdf
from datagen.synthea_loader import load_lab_visits

TEMPLATES: dict[Lang, tuple[str, ...]] = {"en": ("lab_en_01",), "fr": ("lab_fr_01",)}


def sample(visits: Iterable[SourceLabVisit], k: int, rng: random.Random) -> list[SourceLabVisit]:
    """Reservoir sampling: a uniform sample of k visits while holding only k in memory."""
    chosen: list[SourceLabVisit] = []
    for i, visit in enumerate(visits):
        if i < k:
            chosen.append(visit)
        else:
            j = rng.randint(0, i)
            if j < k:
                chosen[j] = visit
    return chosen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthea", type=Path, default=Path("data/synthea/csv"))
    parser.add_argument("--out", type=Path, default=Path("data/docs"))
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fr-share", type=float, default=0.5)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    fake = Faker("fr_FR")
    fake.seed_instance(args.seed)

    pdf_dir = args.out / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()
    with (args.out / "labels.jsonl").open("w", encoding="utf-8") as out:
        for visit in sample(load_lab_visits(args.synthea), args.n, rng):
            lang: Lang = "fr" if rng.random() < args.fr_share else "en"
            template = rng.choice(TEMPLATES[lang])
            report = compose_report(visit, lang, template, rng, fake)
            pdf = render_pdf(report)
            text = extract_text(pdf)
            spans = locate_spans(text, report)
            (pdf_dir / f"{report.doc_id}.pdf").write_bytes(pdf)
            doc = LabeledDoc(
                doc_id=report.doc_id,
                lang=lang,
                template=template,
                source_visit=visit.visit_id,
                text=text,
                spans=spans,
                report=report,
            )
            out.write(doc.model_dump_json() + "\n")
            counts[lang] += 1
            counts["spans"] += len(spans)
    print(f"documents: en={counts['en']} fr={counts['fr']}  spans: {counts['spans']}")


if __name__ == "__main__":
    main()
