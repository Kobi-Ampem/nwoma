import random

from datagen.align import project_spans
from datagen.layouts import LAYOUTS
from datagen.models import EntityType, Span
from datagen.render import render_pdf
from datagen.scan import degrade, images_to_pdf
from ocr.text_layer import OCR_DPI, pdf_pages_as_images, read_pdf
from tests.test_datagen import _report


def _span(text: str, start: int, label: EntityType = "TEST_VALUE") -> Span:
    return Span(label=label, row=0, text=text, value=text, start=start, end=start + len(text))


def test_projection_follows_ocr_errors() -> None:
    source = "Potassium 4.2 mmol/L 3.5 - 5.1"
    target = "Potassiurn 4,2 mmo1/L 3.5 - 5.1"
    spans = [_span("Potassium", 0, "TEST_NAME"), _span("4.2", 10), _span("mmol/L", 14, "TEST_UNIT")]
    projected, lost = project_spans(source, spans, target)
    assert lost == 0
    assert [p.text for p in projected] == ["Potassiurn", "4,2", "mmo1/L"]
    assert [p.value for p in projected] == ["Potassium", "4.2", "mmol/L"]  # truth is kept
    for p in projected:
        assert target[p.start : p.end] == p.text


def test_projection_reports_spans_ocr_deleted() -> None:
    projected, lost = project_spans("Flag H end", [_span("H", 5, "FLAG")], "Flag end")
    assert projected == [] and lost == 1


def test_projection_drops_spans_stretched_over_ocr_junk() -> None:
    # OCR turned the flag and its neighbours into noise; the flag must not cover the noise.
    projected, lost = project_spans(
        "Glucose 140 H\nUrea 5", [_span("H", 12, "FLAG")], "Glucose 140 ee oe a\nfo ee Urea 5"
    )
    assert projected == [] and lost == 1


def test_projection_keeps_a_short_misread() -> None:
    projected, lost = project_spans("Flag \u2193 end", [_span("\u2193", 5, "FLAG")], "Flag 4 end")
    assert lost == 0 and projected[0].text == "4"


def test_scanned_pdf_has_no_text_layer_and_is_read_by_ocr() -> None:
    pdf = render_pdf(_report(LAYOUTS["lab_en_01"]))
    pages = [degrade(p, random.Random(0)) for p in pdf_pages_as_images(pdf, OCR_DPI)]
    text, source = read_pdf(images_to_pdf(pages, OCR_DPI))
    assert source == "ocr"
    assert "Potassium" in text


def test_projection_excludes_junk_ocr_inserts_after_a_span() -> None:
    projected, _ = project_spans("4.2 mmol/L", [_span("4.2", 0)], "4.2| mmol/L")
    assert projected[0].text == "4.2"


def test_projection_keeps_a_whole_replacement_at_the_span_end() -> None:
    # "m" read as "rn" at the end of the unit.
    projected, _ = project_spans("x mmol/L y", [_span("mmol/L", 2, "TEST_UNIT")], "x rnmol/L y")
    assert projected[0].text == "rnmol/L"


def test_projection_survives_many_to_one_replacement() -> None:
    # "rn" in the source collapses to "m" in OCR inside the span.
    projected, lost = project_spans("a Burns b", [_span("Burns", 2, "PATIENT_NAME")], "a Bums b")
    assert lost == 0 and projected[0].text == "Bums"
