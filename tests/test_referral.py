import random
from datetime import date
from pathlib import Path

import pytest
from faker import Faker

from datagen.models import LabeledDoc, ReferralLetter, SourcePatient, SourceReferral
from datagen.referral import (
    REFERRAL_LAYOUTS,
    compose_referral,
    locate_referral_spans,
    referral_layouts_for,
    render_referral,
)
from datagen.referral_catalogue import CONDITIONS
from evals.score import all_correct, prf, score_doc
from extract.schema import ExtractedMedication, Extraction
from ocr.text_layer import pdf_text

_ICD10_FILE = Path("data/icd10cm/Code Descriptions/icd10cm_order_2027.txt")


def _source() -> SourceReferral:
    return SourceReferral(
        visit_id="visit-1",
        patient_id="patient-1",
        patient=SourcePatient(given="Ama", family="Mensah", birth_date=date(1961, 2, 3), sex="F"),
        written_on=date(2025, 6, 4),
        clinician="Kwame Boateng",
        organisation="Kumasi Family Practice",
        conditions=["44054006", "59621000", "55822004", "271737000"],
        medications=[
            "24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet",
            "amLODIPine 2.5 MG Oral Tablet",
            "Acetaminophen 300 MG / Hydrocodone Bitartrate 5 MG Oral Tablet",
        ],
        allergies=["Penicillin V", "Peanut (substance)"],
    )


def _doc(layout: str) -> LabeledDoc:
    fake = Faker("fr_FR")
    fake.seed_instance(1)
    letter = compose_referral(_source(), REFERRAL_LAYOUTS[layout], random.Random(1), fake)
    text = pdf_text(render_referral(letter))
    return LabeledDoc(
        doc_id=letter.doc_id,
        split="test",
        source="digital",
        lost_spans=0,
        lang=letter.lang,
        template=layout,
        source_visit="visit-1",
        text=text,
        spans=locate_referral_spans(text, letter),
        report=letter,
    )


def _oracle(letter: ReferralLetter) -> Extraction:
    return Extraction(
        patient_name=letter.patient_name.text,
        birth_date=letter.birth_date.text,
        sex=letter.sex.text,
        clinician=letter.clinician.text,
        reason=letter.reason.text,
        diagnoses=[d.text for d in letter.diagnoses],
        medications=[
            ExtractedMedication(name=m.name.text, dose=m.dose.text, frequency=m.frequency.text)
            for m in letter.medications
        ],
        allergies=[a.text for a in letter.allergies],
    )


@pytest.mark.parametrize("layout", sorted(REFERRAL_LAYOUTS))
def test_every_field_is_labelled_where_it_is_printed(layout: str) -> None:
    doc = _doc(layout)
    assert all(doc.text[s.start : s.end] == s.text for s in doc.spans)
    labels = {s.label for s in doc.spans}
    assert {"PATIENT_NAME", "REASON", "DIAGNOSIS", "MEDICATION", "DOSE", "ALLERGY"} <= labels


@pytest.mark.parametrize("layout", sorted(REFERRAL_LAYOUTS))
def test_a_perfect_extraction_scores_one(layout: str) -> None:
    doc = _doc(layout)
    assert isinstance(doc.report, ReferralLetter)
    counts = score_doc(doc, _oracle(doc.report))
    assert all_correct(counts) and prf(counts) == (1.0, 1.0, 1.0)


def test_a_missed_allergy_costs_only_that_allergy() -> None:
    doc = _doc("ref_en_01")
    assert isinstance(doc.report, ReferralLetter)
    ext = _oracle(doc.report)
    ext.allergies = ext.allergies[1:]
    counts = score_doc(doc, ext)
    assert counts["ALLERGY/fn"] == 1 and counts["ALLERGY/fp"] == 0
    assert counts["DIAGNOSIS/fn"] == 0


def test_heldout_referral_layouts_use_a_skeleton_training_never_sees() -> None:
    for lang in ("en", "fr"):
        train = {lay.skeleton for lay in referral_layouts_for(lang, "train")}
        heldout = {lay.skeleton for lay in referral_layouts_for(lang, "heldout")}
        assert heldout and train.isdisjoint(heldout)


@pytest.mark.skipif(not _ICD10_FILE.exists(), reason="ICD-10-CM file not downloaded")
def test_every_catalogue_code_is_a_billable_icd10cm_code() -> None:
    billable = {
        line[6:13].strip() for line in _ICD10_FILE.open(encoding="utf-8") if line[14] == "1"
    }
    assert {c.icd10.replace(".", "") for c in CONDITIONS.values()} <= billable
