"""Regression tests for the issues the Codex audit found (22 Oct 2026). Each test is named after
the failure it prevents."""

import io
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from api.fhir import FhirRequest, build_bundle
from api.service import Nwoma, UnsupportedDocument
from datagen.render import render_pdf
from extract.cascade import Cascade
from extract.llm import GeminiExtractor
from extract.schema import ExtractedResult, Extraction
from extract.validate import validate
from normalise.fields import parse_number, parse_range
from ocr.text_layer import MAX_PAGES, UnreadableDocument, read_pdf
from tests.test_datagen import _report

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def _ext(**fields: Any) -> Extraction:
    base: dict[str, Any] = {"patient_name": "Ama Mensah", "birth_date": "05/04/1990", "sex": "F"}
    base |= {"clinician": None} | fields
    return Extraction(**base)


def _resources(bundle: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == kind]


# 6. Negative numbers kept their sign.
def test_negative_ranges_keep_their_sign() -> None:
    assert parse_range("-5 - -1") == (-5.0, -1.0)
    assert parse_range("10 - 5") is None  # reversed bounds are not a range
    assert parse_number("-0,5") == -0.5


def test_a_negative_result_is_a_number_to_the_validator() -> None:
    row = ExtractedResult(test_name="Base excess", value="-3", unit="mmol/L",
                          ref_range="-2 - 2", flag="L")  # fmt: skip
    ext = _ext(collection_date="21/03/2024", results=[row])
    assert validate(ext, "lab") == []


# 7. Impossible dates and non-finite numbers in the FHIR export.
def test_fhir_drops_impossible_dates_and_non_finite_values() -> None:
    row = ExtractedResult(
        test_name="Glucose", value="NaN", unit="mg/dL", ref_range="-5 - -1", flag=None
    )
    ext = _ext(birth_date="31/02/2024", results=[row])
    bundle = build_bundle(FhirRequest(doc_id="d", doc_type="lab", extraction=ext), NOW)
    assert "birthDate" not in _resources(bundle, "Patient")[0]
    obs = _resources(bundle, "Observation")[0]
    assert obs["valueString"] == "NaN"  # kept as printed, not a broken number
    rng = obs["referenceRange"][0]
    assert (rng["low"]["value"], rng["high"]["value"]) == (-5.0, -1.0)


# 5. A coded resource is human-verified only if its code was confirmed too.
def test_provenance_needs_the_code_confirmed() -> None:
    ext = _ext(diagnoses=["Obesity"])
    req = FhirRequest(doc_id="d", doc_type="referral", extraction=ext,
                      codes={"diagnoses[0]": "E66.9"}, confirmed=["diagnoses[0]"],
                      reviewer="Dr R")  # fmt: skip
    verified = _resources(build_bundle(req, NOW), "Provenance")
    assert len(verified) == 1  # software only: the code was not confirmed
    req.confirmed.append("diagnoses[0].code")
    _, human = _resources(build_bundle(req, NOW), "Provenance")
    assert len(human["target"]) == 1


# 11. Malformed PDFs, and 2. work limits.
def test_a_damaged_pdf_is_a_clear_error() -> None:
    with pytest.raises(UnreadableDocument, match="damaged or encrypted"):
        read_pdf(b"%PDF-broken")


def test_too_many_pages_are_refused() -> None:
    page = Image.new("L", (200, 280), 255)
    buffer = io.BytesIO()
    page.save(buffer, format="PDF", save_all=True, append_images=[page] * MAX_PAGES)
    with pytest.raises(UnreadableDocument, match="pages"):
        read_pdf(buffer.getvalue())


def test_ocr_stops_when_the_document_budget_is_spent(monkeypatch: pytest.MonkeyPatch) -> None:
    # 25 Oct audit: 5 pages x 30 s of OCR alone could pass Lambda's 120 s limit.
    monkeypatch.setattr("ocr.text_layer.OCR_BUDGET_S", 0)
    page = Image.new("L", (200, 280), 255)  # blank, so it needs OCR
    buffer = io.BytesIO()
    page.save(buffer, format="PDF")
    with pytest.raises(UnreadableDocument, match="too long"):
        read_pdf(buffer.getvalue())


def test_the_service_turns_unreadable_files_into_client_errors() -> None:
    service = Nwoma.__new__(Nwoma)  # read() needs no models
    with pytest.raises(UnsupportedDocument):
        service.read(b"%PDF-broken")
    with pytest.raises(UnsupportedDocument):
        service.read(b"not a document")


# 8. A digital page must not hide a scanned one.
def test_mixed_pdf_reads_scanned_pages_too() -> None:
    import base64

    import weasyprint

    from datagen.layouts import LAYOUTS
    from ocr.text_layer import pdf_pages_as_images

    # Page 1: real text. Page 2: only an image of a report page, like a scan (no text layer).
    scan = pdf_pages_as_images(render_pdf(_report(LAYOUTS["lab_en_01"])), 150)[0]
    buffer = io.BytesIO()
    scan.save(buffer, format="PNG")
    image = base64.b64encode(buffer.getvalue()).decode()
    html = (
        "<p>Cover letter: please find the laboratory results attached overleaf.</p>"
        '<img style="display: block; break-before: page; width: 100%" '
        f'src="data:image/png;base64,{image}">'
    )
    text, source = read_pdf(weasyprint.HTML(string=html).write_pdf())
    assert source == "ocr" and "Cover letter" in text and "Potassium" in text


# 9. An LLM failure keeps the local answer.
def test_an_llm_outage_keeps_the_ner_answer() -> None:
    class _Ner:
        def extract(self, text: str) -> Extraction:
            row = ExtractedResult(test_name="Creatinine", value="1.62", unit="mg/dL",
                                  ref_range="0.60 - 1.30", flag=None)  # fmt: skip
            return _ext(collection_date="21/03/2024", results=[row])

    class _BrokenLlm:
        def extract(self, *_: Any) -> Any:
            raise ConnectionError("Gemini unreachable")

    result = Cascade(_Ner(), _BrokenLlm()).run("d", "Biochemistry result")  # type: ignore[arg-type]
    assert result.source == "ner" and result.issues
    assert "ConnectionError" in result.notes[0]


# 4. The API stores nothing.
def test_an_uncached_extractor_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    reply = ('{"patient_name": "A", "birth_date": null, "sex": null, "clinician": null, '
             '"results": []}')  # fmt: skip
    from types import SimpleNamespace

    client: Any = SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda **_: SimpleNamespace(text=reply, usage_metadata=None)))  # fmt: skip
    GeminiExtractor("m", None, client=client).extract("d", "Biochemistry result 140 mmol/L")
    assert list(tmp_path.rglob("*")) == []
