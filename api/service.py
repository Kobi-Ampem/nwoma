"""Everything the API and the MCP server do, loaded once: read a document, run the cascade,
suggest codes. Both front ends are thin wrappers, so they always behave the same.

Nothing is stored: a document is read, answered and forgotten.
"""

import hashlib
import os
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from extract.cascade import Cascade
from extract.doctype import DocType
from extract.llm import GeminiExtractor
from extract.ner import NerExtractor
from extract.schema import Extraction
from normalise.embed import Embedder
from normalise.icd10 import Icd10Mapper
from normalise.loinc import LoincMapper
from ocr.text_layer import UnreadableDocument, read_image, read_pdf

MAX_BYTES = 5 * 1024 * 1024


class CodeSuggestion(BaseModel):
    code: str
    display: str


class IssueOut(BaseModel):
    field: str
    kind: str
    message: str


class ExtractResponse(BaseModel):
    doc_id: str
    doc_type: DocType
    text_source: Literal["text_layer", "ocr"]
    text: str  # what the extractor read: the review screen highlights fields in it
    extraction: Extraction
    extractor: Literal["ner", "llm"]
    issues: list[IssueOut]  # fields the reviewer should check
    codes: dict[str, list[CodeSuggestion]]  # 'results[3]' / 'diagnoses[0]' -> top 5 codes
    llm_enabled: bool
    notes: list[str]
    seconds: float


class UnsupportedDocument(ValueError):
    pass


class Nwoma:
    def __init__(
        self,
        model_dir: Path = Path("models/ner"),
        loinc_dir: Path = Path("data/loinc"),
        icd10_file: Path = Path("data/icd10cm/Code Descriptions/icd10cm_order_2027.txt"),
        cache_dir: Path = Path("data/cache"),
        llm_model: str | None = None,
    ) -> None:
        embed = Embedder().encode
        self.loinc = LoincMapper(loinc_dir, embed, cache_dir / "loinc_names.npy")
        self.icd10 = Icd10Mapper(icd10_file, embed, cache_dir / "icd10_names.npy")
        # The LLM fallback switches on only when a key is configured (the Free tier has none;
        # the deployed parameter holds 'none' until a key is set).
        llm = None
        if os.environ.get("GEMINI_API_KEY", "none").strip() not in ("", "none"):
            model = llm_model or os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
            # No disk cache (nothing is stored) and a short budget: 2 tries of 25 s at most, so a
            # Gemini outage ends in the local answer well inside Lambda's 120 s timeout.
            llm = GeminiExtractor(model, None, retries=2, timeout_ms=25_000)
        self.cascade = Cascade(NerExtractor.from_onnx(model_dir), llm)

    @property
    def llm_enabled(self) -> bool:
        return self.cascade.llm is not None

    def read(self, data: bytes, filename: str = "") -> tuple[str, Literal["text_layer", "ocr"]]:
        if len(data) > MAX_BYTES:
            raise UnsupportedDocument("documents are limited to 5 MB")
        try:
            if data[:5] == b"%PDF-":
                return read_pdf(data)
            return read_image(data), "ocr"
        except UnreadableDocument as e:
            raise UnsupportedDocument(str(e)) from e

    def extract(self, data: bytes, filename: str = "") -> ExtractResponse:
        start = time.perf_counter()
        doc_id = hashlib.sha256(data).hexdigest()[:12]
        text, text_source = self.read(data, filename)
        result = self.cascade.run(doc_id, text)
        return ExtractResponse(
            doc_id=doc_id,
            doc_type=result.doc_type,
            text_source=text_source,
            text=text,
            extraction=result.extraction,
            extractor=result.source,
            issues=[IssueOut(**i.__dict__) for i in result.issues],
            codes=self.suggest_codes(result.extraction),
            llm_enabled=self.llm_enabled,
            notes=result.notes,
            seconds=time.perf_counter() - start,
        )

    def suggest_codes(self, ext: Extraction) -> dict[str, list[CodeSuggestion]]:
        """Top 5 codes per lab result and diagnosis: the reviewer picks, the mapper suggests."""
        codes: dict[str, list[CodeSuggestion]] = {}
        for i, r in enumerate(ext.results):
            if r.test_name:
                codes[f"results[{i}]"] = self.lab_codes(r.test_name, r.unit)
        for i, d in enumerate(ext.diagnoses):
            codes[f"diagnoses[{i}]"] = self.diagnosis_codes(d)
        return codes

    def lab_codes(self, name: str, unit: str | None = None) -> list[CodeSuggestion]:
        return [
            CodeSuggestion(code=h.code, display=self.loinc.rows[h.code]["LONG_COMMON_NAME"])
            for h in self.loinc.map(name, unit)
        ]

    def diagnosis_codes(self, diagnosis: str) -> list[CodeSuggestion]:
        return [
            CodeSuggestion(code=h.code, display=self.icd10.descriptions[h.code])
            for h in self.icd10.map(diagnosis)
        ]
