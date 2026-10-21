"""Turn a reviewed extraction into a FHIR R4 Bundle, with Provenance recording what a human
confirmed.

Values are normalised on the way (ISO dates, dot decimals, H/L interpretation codes). Every
resource gets a stable urn:uuid derived from the document, so the same input gives the same
Bundle. Two Provenance records: one says Nwoma assembled every resource; the other, only when a
reviewer confirmed something, names the resources whose fields were all confirmed.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from extract.doctype import DocType
from extract.schema import Extraction
from normalise.fields import (
    norm_clinician,
    norm_date,
    norm_flag,
    norm_name,
    norm_number,
    norm_range,
)
from normalise.retrieval import fold

LOINC = "http://loinc.org"
ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"
SNOMED = "http://snomed.info/sct"
_INTERPRETATION = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
_PROVENANCE_AGENT = "http://terminology.hl7.org/CodeSystem/provenance-participant-type"


class FhirRequest(BaseModel):
    doc_id: str
    doc_type: DocType
    extraction: Extraction  # as reviewed
    codes: dict[str, str] = {}  # 'results[3]' / 'diagnoses[0]' -> the code the reviewer kept
    confirmed: list[str] = []  # field paths the reviewer confirmed, e.g. 'results[3].value'
    reviewer: str | None = None


def build_bundle(req: FhirRequest, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, f"nwoma:{req.doc_id}")
    entries: list[dict[str, Any]] = []
    fields_of: dict[str, list[str]] = {}  # resource url -> field paths it carries

    def add(resource: dict[str, Any], key: str, fields: list[str]) -> str:
        url = f"urn:uuid:{uuid.uuid5(namespace, key)}"
        entries.append({"fullUrl": url, "resource": resource})
        fields_of[url] = fields
        return url

    ext = req.extraction
    patient = add(_patient(ext), "patient", ["patient_name", "birth_date", "sex"])
    practitioner = (
        add(
            {"resourceType": "Practitioner", "name": [{"text": norm_clinician(ext.clinician)}]},
            "practitioner",
            ["clinician"],
        )
        if ext.clinician
        else None
    )
    subject = {"reference": patient}
    if req.doc_type == "lab":
        observations = [
            add(_observation(req, i, subject), f"results[{i}]", _row_fields(i))
            for i in range(len(ext.results))
        ]
        report: dict[str, Any] = {
            "resourceType": "DiagnosticReport",
            "status": "final",
            "code": {
                "coding": [{"system": LOINC, "code": "11502-2", "display": "Laboratory report"}]
            },
            "subject": subject,
            "result": [{"reference": o} for o in observations],
        }
        if (collected := _date(ext.collection_date)) is not None:
            report["effectiveDateTime"] = collected
        if practitioner:
            report["performer"] = [{"reference": practitioner}]
        add(report, "report", ["collection_date"])
    else:
        conditions = [
            add(_condition(req, i, subject), f"diagnoses[{i}]", [f"diagnoses[{i}]"])
            for i in range(len(ext.diagnoses))
        ]
        referral: dict[str, Any] = {
            "resourceType": "ServiceRequest",
            "status": "active",
            "intent": "order",
            "code": {
                "coding": [{"system": SNOMED, "code": "3457005", "display": "Patient referral"}]
            },
            "subject": subject,
            "reasonCode": [{"text": ext.reason}] if ext.reason else [],
            "reasonReference": [{"reference": c} for c in conditions],
        }
        if practitioner:
            referral["requester"] = {"reference": practitioner}
        add(referral, "referral", ["reason"])
        for i, m in enumerate(ext.medications):
            dosage = " ".join(p for p in (m.dose, m.frequency) if p)
            statement = {
                "resourceType": "MedicationStatement",
                "status": "active",
                "medicationCodeableConcept": {"text": m.name},
                "subject": subject,
                "dosage": [{"text": dosage}] if dosage else [],
            }
            add(
                statement,
                f"medications[{i}]",
                [f"medications[{i}].{f}" for f in ("name", "dose", "frequency")],
            )
        for i, a in enumerate(ext.allergies):
            allergy = {
                "resourceType": "AllergyIntolerance",
                "code": {"text": a},
                "patient": subject,
            }
            add(allergy, f"allergies[{i}]", [f"allergies[{i}]"])

    targets = [{"reference": e["fullUrl"]} for e in entries]
    add(
        _provenance(targets, now, "assembler", "Nwoma extraction pipeline", device=True), "prov", []
    )
    confirmed = set(req.confirmed)
    verified = [
        {"reference": url}
        for url, fields in fields_of.items()
        if fields and all(f in confirmed for f in fields)
    ]
    if req.reviewer and verified:
        add(_provenance(verified, now, "verifier", req.reviewer, device=False), "prov-human", [])
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": now.isoformat(),
        "entry": entries,
    }


def _row_fields(i: int) -> list[str]:
    return [f"results[{i}].{f}" for f in ("test_name", "value", "unit", "ref_range", "flag")]


def _date(text: str | None) -> str | None:
    if not text:
        return None
    iso = norm_date(text)
    return iso if len(iso) == 10 and iso[4] == "-" else None


def _patient(ext: Extraction) -> dict[str, Any]:
    patient: dict[str, Any] = {"resourceType": "Patient"}
    if ext.patient_name:
        given, _, family = norm_name(ext.patient_name).rpartition(" ")
        patient["name"] = [
            {"text": ext.patient_name, "family": family.title() if family.isupper() else family}
            | ({"given": [given]} if given else {})
        ]
    if (birth := _date(ext.birth_date)) is not None:
        patient["birthDate"] = birth
    if ext.sex:
        sex = fold(ext.sex)[:1]
        patient["gender"] = {"m": "male", "f": "female", "h": "male"}.get(sex, "unknown")
    return patient


def _observation(req: FhirRequest, i: int, subject: dict[str, str]) -> dict[str, Any]:
    r = req.extraction.results[i]
    code: dict[str, Any] = {"text": r.test_name}
    if chosen := req.codes.get(f"results[{i}]"):
        code["coding"] = [{"system": LOINC, "code": chosen}]
    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "status": "final",
        "category": [
            {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                        "code": "laboratory",
                    }
                ]
            }
        ],
        "code": code,
        "subject": subject,
    }
    try:
        quantity: dict[str, Any] = {"value": float(norm_number(r.value))}
        if r.unit:
            quantity["unit"] = r.unit
        obs["valueQuantity"] = quantity
    except ValueError:
        obs["valueString"] = r.value  # not a number: kept as printed, for the reviewer
    if r.ref_range:
        low, sep, high = norm_range(r.ref_range).partition("-")
        bounds: dict[str, Any] = {"text": r.ref_range}
        try:
            if sep and low:
                bounds["low"] = {"value": float(low)} | ({"unit": r.unit} if r.unit else {})
            if sep and high:
                bounds["high"] = {"value": float(high)} | ({"unit": r.unit} if r.unit else {})
        except ValueError:
            pass
        obs["referenceRange"] = [bounds]
    if r.flag and (flag := norm_flag(r.flag)) in ("H", "L"):
        display = "High" if flag == "H" else "Low"
        obs["interpretation"] = [
            {"coding": [{"system": _INTERPRETATION, "code": flag, "display": display}]}
        ]
    return obs


def _condition(req: FhirRequest, i: int, subject: dict[str, str]) -> dict[str, Any]:
    code: dict[str, Any] = {"text": req.extraction.diagnoses[i]}
    if chosen := req.codes.get(f"diagnoses[{i}]"):
        code["coding"] = [{"system": ICD10CM, "code": chosen}]
    return {
        "resourceType": "Condition",
        "clinicalStatus": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active",
                }
            ]
        },
        "code": code,
        "subject": subject,
    }


def _provenance(
    targets: list[dict[str, str]], now: datetime, role: str, who: str, device: bool
) -> dict[str, Any]:
    return {
        "resourceType": "Provenance",
        "target": targets,
        "recorded": now.isoformat(),
        "agent": [
            {
                "type": {"coding": [{"system": _PROVENANCE_AGENT, "code": role}]},
                "who": {"display": who, "type": "Device" if device else "Practitioner"},
            }
        ],
    }
