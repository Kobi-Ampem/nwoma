"""A perfect extraction of a labelled document: every field exactly as printed.

Used to test the scorer (a perfect answer must score 1.0) and the validator (a perfect answer
should raise no issues).
"""

from datagen.models import LabeledDoc, LabReport
from extract.schema import ExtractedMedication, ExtractedResult, Extraction


def oracle(doc: LabeledDoc) -> Extraction:
    r = doc.report
    if isinstance(r, LabReport):
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
    return Extraction(
        patient_name=r.patient_name.text,
        birth_date=r.birth_date.text,
        sex=r.sex.text,
        clinician=r.clinician.text,
        reason=r.reason.text,
        diagnoses=[d.text for d in r.diagnoses],
        medications=[
            ExtractedMedication(name=m.name.text, dose=m.dose.text, frequency=m.frequency.text)
            for m in r.medications
        ],
        allergies=[a.text for a in r.allergies],
    )
