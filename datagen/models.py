"""Data shapes for generated documents and their labels.

Every extractable field is a `Field`: `text` is exactly what is printed on the document, `value` is
the normalised truth the evaluation compares against (ISO dates, dot decimals, LOINC codes).
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel

Lang = Literal["en", "fr"]
Sex = Literal["M", "F"]

# Entity types the extractor learns to find.
EntityType = Literal[
    "PATIENT_NAME",
    "BIRTH_DATE",
    "SEX",
    "COLLECTION_DATE",
    "CLINICIAN",
    "TEST_NAME",
    "TEST_VALUE",
    "TEST_UNIT",
    "REF_RANGE",
    "FLAG",
]


class Field(BaseModel):
    text: str
    value: str


class SourcePatient(BaseModel):
    """A patient as Synthea describes them, before any language-specific rendering."""

    given: str
    family: str
    birth_date: date
    sex: Sex


class SourceResult(BaseModel):
    loinc: str  # canonical code from the catalogue
    value: float  # in the US units Synthea uses


class SourceLabVisit(BaseModel):
    visit_id: str
    patient: SourcePatient
    collected_on: date
    clinician: str
    organisation: str
    results: list[SourceResult]


class ResultRow(BaseModel):
    panel: str
    name: Field  # value = canonical LOINC code
    value: Field
    unit: Field | None  # some tests (urine pH, specific gravity) print no unit
    ref_range: Field | None
    flag: Field | None


class LabReport(BaseModel):
    doc_id: str
    lang: Lang
    template: str
    lab_name: str
    patient_name: Field
    birth_date: Field
    sex: Field
    collected_on: Field
    clinician: Field
    results: list[ResultRow]


class Span(BaseModel):
    label: EntityType
    row: int | None  # result row index for test fields, None for header fields
    text: str
    value: str
    start: int
    end: int


class LabeledDoc(BaseModel):
    doc_id: str
    lang: Lang
    template: str
    source_visit: str
    text: str
    spans: list[Span]
    report: LabReport
