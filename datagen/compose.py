"""Turn a language-neutral Synthea visit into a printed lab report for one layout."""

import hashlib
import random

from faker import Faker

from datagen.catalogue import BY_CODE, CATALOGUE, PANEL_ORDER, LabTest
from datagen.formatting import fmt_date, fmt_flag, fmt_name, fmt_number, fmt_range, fmt_sex
from datagen.layouts import Layout
from datagen.models import Field, LabReport, ResultRow, SourceLabVisit

_CATALOGUE_INDEX = {t.loinc: i for i, t in enumerate(CATALOGUE)}


def _doc_id(visit_id: str, layout: str) -> str:
    return hashlib.sha256(f"{visit_id}|{layout}".encode()).hexdigest()[:12]


def _result_row(test: LabTest, raw: float, layout: Layout, rng: random.Random) -> ResultRow:
    lang = layout.lang
    factor = test.fr_factor if lang == "fr" else 1.0
    decimals = test.decimals_fr if lang == "fr" else test.decimals_en
    value = round(raw * factor, decimals)
    low = round(test.low * factor, decimals) if test.low is not None else None
    high = round(test.high * factor, decimals) if test.high is not None else None

    low_text = fmt_number(low, decimals, lang) if low is not None else None
    high_text = fmt_number(high, decimals, lang) if high is not None else None
    range_text = fmt_range(low_text, high_text)

    # Flags compare the printed (rounded) value with the printed range on purpose: a document must
    # agree with itself. Flagging the raw 145.4 against 145 would print "145  136 - 145  H".
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
                value=f"{low if low is not None else ''}-{high if high is not None else ''}",
            )
            if range_text
            else None
        ),
        flag=Field(text=fmt_flag(flag, lang, layout.flag_style), value=flag) if flag else None,
    )


def compose_report(
    visit: SourceLabVisit, layout: Layout, rng: random.Random, fake: Faker
) -> LabReport:
    lang = layout.lang
    patient = visit.patient
    if lang == "fr":
        # Synthea's people are American; French documents get French names.
        given = fake.first_name_female() if patient.sex == "F" else fake.first_name_male()
        family = fake.last_name()
        clinician = fake.name()
        lab_name = f"Laboratoire {fake.last_name()}"
    else:
        given, family = patient.given, patient.family
        clinician = visit.clinician
        lab_name = visit.organisation

    ordered = sorted(
        visit.results,
        key=lambda r: (PANEL_ORDER.index(BY_CODE[r.loinc].panel), _CATALOGUE_INDEX[r.loinc]),
    )
    return LabReport(
        doc_id=_doc_id(visit.visit_id, layout.name),
        lang=lang,
        template=layout.name,
        lab_name=lab_name,
        patient_name=Field(
            text=fmt_name(given, family, layout.name_style), value=f"{given} {family}"
        ),
        birth_date=Field(
            text=fmt_date(patient.birth_date, lang, layout.date_style),
            value=patient.birth_date.isoformat(),
        ),
        sex=Field(text=fmt_sex(patient.sex, lang, layout.sex_style), value=patient.sex),
        collected_on=Field(
            text=fmt_date(visit.collected_on, lang, layout.date_style),
            value=visit.collected_on.isoformat(),
        ),
        clinician=Field(text=clinician, value=clinician),
        results=[_result_row(BY_CODE[r.loinc], r.value, layout, rng) for r in ordered],
    )
