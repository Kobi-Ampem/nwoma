import pytest

from datagen.layouts import LAYOUTS
from datagen.models import LabeledDoc
from datagen.render import locate_spans, render_pdf
from evals.score import all_correct, prf, score_doc
from extract.schema import ExtractedResult, Extraction
from ocr.text_layer import pdf_text
from tests.test_datagen import _report


def _doc(layout: str) -> LabeledDoc:
    report = _report(LAYOUTS[layout])
    text = pdf_text(render_pdf(report))
    return LabeledDoc(
        doc_id=report.doc_id,
        split="test",
        source="digital",
        lost_spans=0,
        lang=report.lang,
        template=layout,
        source_visit="visit-1",
        text=text,
        spans=locate_spans(text, report),
        report=report,
    )


def _oracle(doc: LabeledDoc) -> Extraction:
    """A perfect extraction: every field exactly as printed."""
    r = doc.report
    return Extraction(
        patient_name=r.patient_name.text,
        birth_date=r.birth_date.text,
        sex=r.sex.text,
        collection_date=r.collected_on.text,
        clinician=r.clinician.text,
        results=[
            ExtractedResult(
                test_name=row.name.text,
                value=row.value.text,
                unit=row.unit.text if row.unit else None,
                ref_range=row.ref_range.text if row.ref_range else None,
                flag=row.flag.text if row.flag else None,
            )
            for row in r.results
        ],
    )


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_a_perfect_extraction_scores_one_on_every_layout(layout: str) -> None:
    doc = _doc(layout)
    counts = score_doc(doc, _oracle(doc))
    assert all_correct(counts)
    assert prf(counts) == (1.0, 1.0, 1.0)


def test_a_wrong_value_is_both_a_false_positive_and_a_false_negative() -> None:
    doc = _doc("lab_en_01")
    ext = _oracle(doc)
    ext.results[0].value = "99.9"
    counts = score_doc(doc, ext)
    assert counts["TEST_VALUE/fp"] == 1 and counts["TEST_VALUE/fn"] == 1
    assert counts["TEST_NAME/tp"] == len(doc.report.results)  # other fields unaffected


def test_a_skipped_row_costs_only_that_row() -> None:
    doc = _doc("lab_fr_01")
    ext = _oracle(doc)
    del ext.results[1]
    counts = score_doc(doc, ext)
    assert counts["TEST_VALUE/fn"] == 1 and counts["TEST_VALUE/fp"] == 0
    assert counts["TEST_VALUE/tp"] == len(doc.report.results) - 1


def test_a_field_ocr_destroyed_is_not_counted_as_missed() -> None:
    doc = _doc("lab_en_02")
    doc.spans = [s for s in doc.spans if s.label != "PATIENT_NAME"]
    ext = _oracle(doc)
    ext.patient_name = None
    assert all_correct(score_doc(doc, ext))


def test_a_misread_short_name_costs_only_the_name() -> None:
    doc = _doc("lab_en_01")
    ext = _oracle(doc)
    ext.results[0].test_name = "ct"  # e.g. 'Cl' through OCR: no name similarity left
    counts = score_doc(doc, ext)
    assert counts["TEST_NAME/fp"] == 1 and counts["TEST_NAME/fn"] == 1
    assert counts["TEST_VALUE/fn"] == 0 and counts["TEST_VALUE/fp"] == 0
