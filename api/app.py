"""Nwoma's HTTP API. Stateless: a document is read, answered and forgotten.

    uv run uvicorn api.app:app --port 8000

POST /extract   a PDF or image (max 5 MB) -> fields, issues for review, code suggestions
POST /codes     fresh code suggestions after a reviewer edits a name, unit or diagnosis
POST /validate  the validator's issues for an extraction as the reviewer has edited it
POST /fhir      a reviewed extraction -> FHIR R4 Bundle with Provenance
GET  /samples   synthetic sample documents to try
GET  /health    liveness, and whether the LLM fallback is on
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api.fhir import FhirRequest, build_bundle
from api.service import (
    MAX_BYTES,
    CodeSuggestion,
    ExtractResponse,
    IssueOut,
    Nwoma,
    UnsupportedDocument,
)
from extract.doctype import DocType
from extract.schema import Extraction
from extract.validate import validate

SAMPLES = Path(__file__).parent / "samples"
load_dotenv()  # local development; in AWS the settings come from the function's environment


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.nwoma = Nwoma()  # models load once, at start-up
    yield


app = FastAPI(title="Nwoma", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "ALLOWED_ORIGINS", "https://kobi-ampem.github.io,http://localhost:5173"
    ).split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _nwoma(request: Request) -> Nwoma:
    service: Nwoma = request.app.state.nwoma
    return service


@app.get("/health")
def health(request: Request) -> dict[str, Any]:
    return {"status": "ok", "llm_enabled": _nwoma(request).llm_enabled}


@app.post("/events")
def events() -> dict[str, str]:
    """Lambda Web Adapter forwards non-HTTP events (the keep-warm schedule) here."""
    return {"status": "warm"}


@app.post("/extract")
def extract(request: Request, file: Annotated[UploadFile, File()]) -> ExtractResponse:
    # A plain def: FastAPI runs it in a worker thread, so OCR and inference never block the
    # server's event loop.
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "documents are limited to 5 MB")
    try:
        return _nwoma(request).extract(data)
    except UnsupportedDocument as e:
        raise HTTPException(415, str(e)) from e


class CodesRequest(BaseModel):
    kind: Literal["lab", "diagnosis"]
    text: str = Field(max_length=200)
    unit: str | None = Field(default=None, max_length=40)


@app.post("/codes")
def codes(request: Request, req: CodesRequest) -> list[CodeSuggestion]:
    """Fresh suggestions after a reviewer edits a test name, unit or diagnosis: the codes
    chosen for the old text must not survive the edit."""
    service = _nwoma(request)
    if req.kind == "lab":
        return service.lab_codes(req.text, req.unit)
    return service.diagnosis_codes(req.text)


class ValidateRequest(BaseModel):
    doc_type: DocType
    extraction: Extraction


@app.post("/validate")
def check(req: ValidateRequest) -> list[IssueOut]:
    """The same checks as at extraction, run again on the reviewer's edits: a fixed field stops
    being flagged, and an edit that breaks one (a flag the new value contradicts) is caught."""
    return [IssueOut(**i.__dict__) for i in validate(req.extraction, req.doc_type)]


@app.post("/fhir")
def fhir(req: FhirRequest) -> dict[str, Any]:
    return build_bundle(req)


@app.get("/samples")
def samples() -> list[dict[str, str]]:
    return [{"name": p.name, "url": f"/samples/{p.name}"} for p in sorted(SAMPLES.glob("*.pdf"))]


@app.get("/samples/{name}")
def sample(name: str) -> FileResponse:
    path = SAMPLES / name
    if path.suffix != ".pdf" or path.parent != SAMPLES or not path.is_file():
        raise HTTPException(404, "no such sample")
    return FileResponse(path, media_type="application/pdf")
