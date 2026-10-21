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
    # Referral letters
    "REASON",
    "DIAGNOSIS",
    "MEDICATION",
    "DOSE",
    "FREQUENCY",
    "ALLERGY",
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
    patient_id: str
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
    doc_type: Literal["lab"] = "lab"
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


class SourceReferral(BaseModel):
    """A patient's state at their latest visit, before any language-specific rendering."""

    visit_id: str
    patient_id: str
    patient: SourcePatient
    written_on: date
    clinician: str
    organisation: str
    conditions: list[str]  # SNOMED codes in the referral catalogue, most relevant first
    medications: list[str]  # Synthea medication descriptions in the catalogue
    allergies: list[str]  # Synthea allergy descriptions in the catalogue


class MedicationRow(BaseModel):
    name: Field  # value = English generic name
    dose: Field  # value = dose with a dot decimal, e.g. '2.5 mg'
    frequency: Field  # value = frequency key, e.g. 'bd'


class ReferralLetter(BaseModel):
    doc_type: Literal["referral"] = "referral"
    doc_id: str
    lang: Lang
    template: str
    clinic_name: str
    patient_name: Field
    birth_date: Field
    sex: Field
    clinician: Field  # the referring clinician
    specialty: str  # who the letter is addressed to; not an extracted field
    written: str  # the letter's date as printed; not an extracted field
    reason: Field  # value = the reason as printed
    diagnoses: list[Field]  # value = ICD-10-CM code
    medications: list[MedicationRow]
    allergies: list[Field]  # value = English name


class Span(BaseModel):
    label: EntityType
    row: int | None  # result row index for test fields, None for header fields
    text: str
    value: str
    start: int
    end: int


DataSplit = Literal["train", "dev", "test", "test_unseen"]


class LabeledDoc(BaseModel):
    doc_id: str
    split: DataSplit
    source: Literal["digital", "scan"]
    lost_spans: int  # labels OCR destroyed entirely (scans only)
    lang: Lang
    template: str
    source_visit: str
    text: str
    spans: list[Span]
    report: LabReport | ReferralLetter
