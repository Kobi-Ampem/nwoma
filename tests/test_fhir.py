from datetime import UTC, datetime
from typing import Any

from fhir.resources.R4B.bundle import Bundle

from api.fhir import ICD10CM, LOINC, FhirRequest, build_bundle
from evals.oracle import oracle
from tests.test_referral import _doc as _referral_doc
from tests.test_score import _doc as _lab_doc

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def _resources(bundle: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == kind]


def test_a_lab_report_becomes_a_valid_r4_bundle() -> None:
    doc = _lab_doc("lab_fr_01")
    req = FhirRequest(
        doc_id=doc.doc_id, doc_type="lab", extraction=oracle(doc), codes={"results[0]": "718-7"}
    )
    bundle = build_bundle(req, NOW)
    Bundle.model_validate(bundle)  # raises if not valid FHIR
    obs = _resources(bundle, "Observation")
    assert len(obs) == len(doc.report.results)  # type: ignore[union-attr]
    first = obs[0]
    assert first["code"]["coding"] == [{"system": LOINC, "code": "718-7"}]
    assert first["valueQuantity"]["value"] == 10.2  # '10,2' in the French report
    assert first["interpretation"][0]["coding"][0]["code"] == "L"
    assert _resources(bundle, "Patient")[0]["birthDate"] == "1990-04-05"


def test_a_referral_letter_becomes_a_valid_r4_bundle() -> None:
    doc = _referral_doc("ref_fr_02")
    req = FhirRequest(
        doc_id=doc.doc_id,
        doc_type="referral",
        extraction=oracle(doc),
        codes={"diagnoses[0]": "E11.9"},
    )
    bundle = build_bundle(req, NOW)
    Bundle.model_validate(bundle)
    conditions = _resources(bundle, "Condition")
    assert conditions[0]["code"]["coding"] == [{"system": ICD10CM, "code": "E11.9"}]
    assert len(_resources(bundle, "MedicationStatement")) == 3
    assert len(_resources(bundle, "AllergyIntolerance")) == 2
    referral = _resources(bundle, "ServiceRequest")[0]
    assert len(referral["reasonReference"]) == len(conditions)


def test_provenance_names_only_fully_confirmed_resources() -> None:
    doc = _referral_doc("ref_en_01")
    ext = oracle(doc)
    req = FhirRequest(
        doc_id=doc.doc_id,
        doc_type="referral",
        extraction=ext,
        confirmed=["patient_name", "birth_date", "sex", "diagnoses[0]", "medications[0].name"],
        reviewer="Dr A. Reviewer",
    )
    bundle = build_bundle(req, NOW)
    software, human = _resources(bundle, "Provenance")
    assert software["agent"][0]["who"]["type"] == "Device"
    clinical = [e for e in bundle["entry"] if e["resource"]["resourceType"] != "Provenance"]
    assert len(software["target"]) == len(clinical)  # every clinical resource
    verified = {t["reference"] for t in human["target"]}
    kinds = {e["resource"]["resourceType"] for e in bundle["entry"] if e["fullUrl"] in verified}
    # Patient and the first Condition are fully confirmed; the medication only partly (name only).
    assert kinds == {"Patient", "Condition"} and len(verified) == 2


def test_the_same_input_gives_the_same_bundle() -> None:
    doc = _lab_doc("lab_en_01")
    req = FhirRequest(doc_id=doc.doc_id, doc_type="lab", extraction=oracle(doc))
    assert build_bundle(req, NOW) == build_bundle(req, NOW)
