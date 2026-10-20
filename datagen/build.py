"""Generate labelled synthetic lab reports from Synthea output.

uv run python -m datagen.build --n 50 --seed 42
"""

import argparse
import hashlib
import random
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path

from faker import Faker

from datagen.align import project_spans
from datagen.compose import compose_report
from datagen.layouts import LAYOUTS, layouts_for
from datagen.models import DataSplit, LabeledDoc, Lang, SourceLabVisit
from datagen.render import locate_spans, render_pdf
from datagen.scan import degrade, images_to_pdf
from datagen.synthea_loader import load_lab_visits
from ocr.text_layer import OCR_DPI, ocr_image, pdf_pages_as_images, pdf_text


def sample(
    visits: Iterable[SourceLabVisit], k: int, rng: random.Random, per_patient: int = 2
) -> list[SourceLabVisit]:
    """A uniform sample of k visits, at most `per_patient` from any one patient.

    Visits per patient are heavily skewed (median 1, max 260 in a 5,000-patient run), so
    sampling visits directly would fill the dataset with a few chronically ill patients.
    Each patient keeps a reservoir of `per_patient` visits, so memory stays small.
    """
    pools: dict[str, list[SourceLabVisit]] = {}
    seen: Counter[str] = Counter()
    for visit in visits:
        pool = pools.setdefault(visit.patient_id, [])
        i = seen[visit.patient_id]
        seen[visit.patient_id] += 1
        if i < per_patient:
            pool.append(visit)
        else:
            j = rng.randint(0, i)
            if j < per_patient:
                pool[j] = visit
    candidates = [visit for pool in pools.values() for visit in pool]
    return rng.sample(candidates, min(k, len(candidates)))


def split_for(patient_id: str) -> DataSplit:
    """Assign a split by patient, so one person's visits never appear in two splits.

    A hash makes the assignment stable across runs and sample sizes.
    """
    bucket = int(hashlib.sha256(patient_id.encode()).hexdigest()[:8], 16) % 100
    if bucket < 75:
        return "train"
    if bucket < 82:
        return "dev"
    if bucket < 91:
        return "test"
    return "test_unseen"


@dataclass(frozen=True)
class Job:
    visit: SourceLabVisit
    split: DataSplit
    layout: str
    scan: bool
    seed: int  # per document, so results do not depend on worker scheduling
    pdf_dir: Path


_fake: Faker | None = None


def make_doc(job: Job) -> LabeledDoc:
    global _fake
    if _fake is None:  # one Faker per worker process
        _fake = Faker("fr_FR")
    _fake.seed_instance(job.seed)
    rng = random.Random(job.seed)

    report = compose_report(job.visit, LAYOUTS[job.layout], rng, _fake)
    pdf = render_pdf(report)
    text = pdf_text(pdf)
    spans = locate_spans(text, report)
    lost = 0
    if job.scan:
        pages = [degrade(page, rng) for page in pdf_pages_as_images(pdf, OCR_DPI)]
        pdf = images_to_pdf(pages, OCR_DPI)
        ocr_text = "\n".join(ocr_image(page) for page in pages)
        spans, lost = project_spans(text, spans, ocr_text)
        text = ocr_text
    (job.pdf_dir / f"{report.doc_id}.pdf").write_bytes(pdf)
    return LabeledDoc(
        doc_id=report.doc_id,
        split=job.split,
        source="scan" if job.scan else "digital",
        lost_spans=lost,
        lang=report.lang,
        template=job.layout,
        source_visit=job.visit.visit_id,
        text=text,
        spans=spans,
        report=report,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthea", type=Path, default=Path("data/synthea/csv"))
    parser.add_argument("--out", type=Path, default=Path("data/docs"))
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fr-share", type=float, default=0.5)
    parser.add_argument("--scan-share", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--per-patient", type=int, default=2)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    pdf_dir = args.out / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    for stale in pdf_dir.glob("*.pdf"):  # PDFs from an earlier run have no label any more
        stale.unlink()

    jobs: list[Job] = []
    for visit in sample(load_lab_visits(args.synthea), args.n, rng, args.per_patient):
        split = split_for(visit.patient_id)
        lang: Lang = "fr" if rng.random() < args.fr_share else "en"
        # Only the unseen-layout test split uses held-out layouts.
        layout = rng.choice(layouts_for(lang, "heldout" if split == "test_unseen" else "train"))
        scan = rng.random() < args.scan_share
        jobs.append(Job(visit, split, layout.name, scan, rng.randrange(2**32), pdf_dir))

    counts: Counter[str] = Counter()
    labels_path = args.out / "labels.jsonl"
    with labels_path.open("w", encoding="utf-8") as out, Pool(args.workers) as pool:
        for doc in pool.imap(make_doc, jobs, chunksize=4):
            out.write(doc.model_dump_json() + "\n")
            counts[doc.split] += 1
            counts[doc.lang] += 1
            counts[doc.source] += 1
            counts["spans"] += len(doc.spans)
            counts["lost"] += doc.lost_spans
    print(
        f"documents: en={counts['en']} fr={counts['fr']} "
        f"digital={counts['digital']} scan={counts['scan']}\n"
        f"splits: train={counts['train']} dev={counts['dev']} test={counts['test']} "
        f"test_unseen={counts['test_unseen']}\n"
        f"spans: {counts['spans']}  lost to OCR: {counts['lost']}"
    )


if __name__ == "__main__":
    main()
