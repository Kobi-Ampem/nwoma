"""The HTTP layer with a fake service: no models needed, so it runs anywhere (including CI)."""

from typing import Any

from fastapi.testclient import TestClient

from api.app import app
from api.service import ExtractResponse, UnsupportedDocument
from extract.schema import Extraction


class _FakeNwoma:
    llm_enabled = False

    def extract(self, data: bytes, filename: str = "") -> ExtractResponse:
        if not data.startswith(b"%PDF-"):
            raise UnsupportedDocument("not a PDF or an image")
        ext = Extraction(
            patient_name="Ama Mensah", birth_date="05/04/1990", sex="F", clinician=None
        )
        return ExtractResponse(
            doc_id="abc", doc_type="referral", text_source="text_layer", text="...",
            extraction=ext, extractor="ner", issues=[], codes={}, llm_enabled=False,
            notes=[], seconds=0.1,
        )  # fmt: skip


def _client() -> TestClient:
    client = TestClient(app)  # used without `with`: the lifespan (real models) never runs
    app.state.nwoma = _FakeNwoma()
    return client


def test_health_reports_the_llm_switch() -> None:
    assert _client().get("/health").json() == {"status": "ok", "llm_enabled": False}


def test_extract_returns_the_service_answer() -> None:
    r = _client().post("/extract", files={"file": ("a.pdf", b"%PDF-1.7 ...", "application/pdf")})
    assert r.status_code == 200 and r.json()["extraction"]["patient_name"] == "Ama Mensah"


def test_extract_rejects_other_files_and_large_ones() -> None:
    client = _client()
    assert client.post("/extract", files={"file": ("a.txt", b"hello")}).status_code == 415
    big = b"%PDF-" + b"0" * (5 * 1024 * 1024)
    assert client.post("/extract", files={"file": ("big.pdf", big)}).status_code == 413


def test_fhir_returns_a_bundle() -> None:
    body: dict[str, Any] = {
        "doc_id": "abc",
        "doc_type": "lab",
        "extraction": {"patient_name": "Ama Mensah", "birth_date": "05/04/1990", "sex": "F",
                       "clinician": None},
    }  # fmt: skip
    bundle = _client().post("/fhir", json=body).json()
    assert bundle["resourceType"] == "Bundle"


def test_samples_cannot_escape_their_folder() -> None:
    client = _client()
    names = [s["name"] for s in client.get("/samples").json()]
    assert "lab-report-en-digital.pdf" in names
    assert client.get("/samples/..%2F..%2FREADME.md").status_code == 404


def test_the_keep_warm_ping_is_answered() -> None:
    assert _client().post("/events", json={"source": "aws.events"}).json() == {"status": "warm"}
