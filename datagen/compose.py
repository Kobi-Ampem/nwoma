"""Turn a language-neutral Synthea visit into a printed lab report in English or French."""

import hashlib
import random

from faker import Faker

from datagen.catalogue import BY_CODE, CATALOGUE, PANEL_ORDER, LabTest
from datagen.formatting import fmt_date, fmt_number, fmt_range
from datagen.models import Field, LabReport, Lang, ResultRow, SourceLabVisit

# Header labels printed on the document. The span locator anchors on these strings.
HEADER_LABELS: dict[Lang, dict[str, str]] = {
    "en": {
        "PATIENT_NAME": "Patient name",
        "BIRTH_DATE": "Date of birth",
        "SEX": "Sex",
        "COLLECTION_DATE": "Collected",
        "CLINICIAN": "Requesting clinician",
    },
    "fr": {
        "PATIENT_NAME": "Nom du patient",
        "BIRTH_DATE": "Date de naissance",
        "SEX": "Sexe",
        "COLLECTION_DATE": "Date de prélèvement",
        "CLINICIAN": "Prescripteur",
    },
}

_SEX_TEXT: dict[Lang, dict[str, str]] = {
    "en": {"M": "Male", "F": "Female"},
    "fr": {"M": "Masculin", "F": "Féminin"},
}
# French reports flag low results "B" (bas).
_FLAG_TEXT: dict[Lang, dict[str, str]] = {"en": {"H": "H", "L": "L"}, "fr": {"H": "H", "L": "B"}}

_CATALOGUE_INDEX = {t.loinc: i for i, t in enumerate(CATALOGUE)}


def _doc_id(visit_id: str, lang: Lang, template: str) -> str:
    return hashlib.sha256(f"{visit_id}|{lang}|{template}".encode()).hexdigest()[:12]


def _result_row(test: LabTest, raw: float, lang: Lang, rng: random.Random) -> ResultRow:
    factor = test.fr_factor if lang == "fr" else 1.0
    decimals = test.decimals_fr if lang == "fr" else test.decimals_en
    value = round(raw * factor, decimals)
    low = round(test.low * factor, decimals) if test.low is not None else None
    high = round(test.high * factor, decimals) if test.high is not None else None

    low_text = fmt_number(low, decimals, lang) if low is not None else None
    high_text = fmt_number(high, decimals, lang) if high is not None else None
    range_text = fmt_range(low_text, high_text)

    flag: str | None = None
    if high is not None and value > high:
        flag = "H"
    elif low is not None and value < low:
        flag = "L"

    unit = test.unit_fr if lang == "fr" else test.unit_en
    name = rng.choice(test.names_fr if lang == "fr" else test.names_en)
    return ResultRow(
        panel=test.panel,
        name=Field(text=name, value=test.loinc),
        value=Field(text=fmt_number(value, decimals, lang), value=f"{value:.{decimals}f}"),
        unit=Field(text=unit, value=test.unit_en) if unit else None,
        ref_range=(
            Field(
                text=range_text,
                value=f"{low if low is not None else ''}-" f"{high if high is not None else ''}",
            )
            if range_text
            else None
        ),
        flag=Field(text=_FLAG_TEXT[lang][flag], value=flag) if flag else None,
    )


def compose_report(
    visit: SourceLabVisit, lang: Lang, template: str, rng: random.Random, fake: Faker
) -> LabReport:
    patient = visit.patient
    if lang == "fr":
        # Synthea's people are American; French documents get French names.
        given = fake.first_name_female() if patient.sex == "F" else fake.first_name_male()
        family = fake.last_name()
        name_text = f"{family.upper()} {given}"
        clinician = fake.name()
        lab_name = f"Laboratoire {fake.last_name()}"
    else:
        given, family = patient.given, patient.family
        name_text = f"{given} {family}"
        clinician = visit.clinician
        lab_name = visit.organisation

    ordered = sorted(
        visit.results,
        key=lambda r: (PANEL_ORDER.index(BY_CODE[r.loinc].panel), _CATALOGUE_INDEX[r.loinc]),
    )
    return LabReport(
        doc_id=_doc_id(visit.visit_id, lang, template),
        lang=lang,
        template=template,
        lab_name=lab_name,
        patient_name=Field(text=name_text, value=f"{given} {family}"),
        birth_date=Field(
            text=fmt_date(patient.birth_date, lang), value=patient.birth_date.isoformat()
        ),
        sex=Field(text=_SEX_TEXT[lang][patient.sex], value=patient.sex),
        collected_on=Field(
            text=fmt_date(visit.collected_on, lang), value=visit.collected_on.isoformat()
        ),
        clinician=Field(text=clinician, value=clinician),
        results=[_result_row(BY_CODE[r.loinc], r.value, lang, rng) for r in ordered],
    )
