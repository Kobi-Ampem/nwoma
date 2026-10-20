"""What an extractor returns: each field as printed on the document, before normalisation.

Both extractors (the LLM and the fine-tuned NER model) produce this shape, and the same code in
`normalise.fields` turns it into comparable values, so they are compared on extraction alone.
"""

from pydantic import BaseModel, Field


class ExtractedResult(BaseModel):
    test_name: str = Field(description="Test name as printed, e.g. 'Hémoglobine' or 'Na'")
    value: str = Field(description="Result as printed, e.g. '12,7'")
    unit: str | None = Field(description="Unit as printed, e.g. 'mmol/L'; null if none")
    ref_range: str | None = Field(description="Reference range as printed, e.g. '3,5 - 5,1'")
    flag: str | None = Field(description="Abnormal flag as printed, e.g. 'H', 'Bas', '↑'")


class Extraction(BaseModel):
    patient_name: str | None = Field(description="Patient name as printed")
    birth_date: str | None = Field(description="Date of birth as printed")
    sex: str | None = Field(description="Sex as printed")
    collection_date: str | None = Field(description="Sample collection date as printed")
    clinician: str | None = Field(description="Requesting clinician as printed")
    results: list[ExtractedResult] = Field(description="One entry per test result row")
