import random
from datetime import date

import pytest
from faker import Faker

from datagen.catalogue import BY_CODE, CATALOGUE
from datagen.compose import compose_report
from datagen.formatting import fmt_date, fmt_number, fmt_range
from datagen.models import Lang, SourceLabVisit, SourcePatient, SourceResult
from datagen.render import extract_text, locate_spans, render_pdf


def _visit() -> SourceLabVisit:
    return SourceLabVisit(
        visit_id="visit-1",
        patient=SourcePatient(given="Ama", family="Mensah", birth_date=date(1990, 4, 5), sex="F"),
        collected_on=date(2024, 3, 21),
        clinician="Kwame Boateng",
        organisation="Kumasi Clinical Laboratory",
        results=[
            SourceResult(loinc="718-7", value=10.2),  # low haemoglobin: flagged
            SourceResult(loinc="2823-3", value=4.2),
            SourceResult(loinc="2160-0", value=1.62),  # high creatinine, converted in French
            SourceResult(loinc="2345-7", value=88.0),  # glucose, mg/dL vs g/L
            SourceResult(loinc="5803-2", value=6.0),  # urine pH: no unit
            SourceResult(loinc="2093-3", value=231.0),  # high cholesterol, upper bound only
            SourceResult(loinc="5792-7", value=0.0),  # urine glucose: no reference range
        ],
    )


@pytest.mark.parametrize("lang", ["en", "fr"])
def test_every_span_matches_the_pdf_text(lang: Lang) -> None:
    fake = Faker("fr_FR")
    fake.seed_instance(1)
    report = compose_report(_visit(), lang, f"lab_{lang}_01", random.Random(1), fake)
    text = extract_text(render_pdf(report))
    spans = locate_spans(text, report)

    for span in spans:
        assert text[span.start : span.end] == span.text

    labels = [s.label for s in spans]
    assert labels.count("TEST_NAME") == len(report.results)
    assert labels.count("TEST_VALUE") == len(report.results)
    assert labels.count("FLAG") == 3
    assert labels.count("TEST_UNIT") == 6  # urine pH prints no unit
    assert {"PATIENT_NAME", "BIRTH_DATE", "SEX", "COLLECTION_DATE", "CLINICIAN"} <= set(labels)


def test_french_report_converts_units_and_uses_decimal_comma() -> None:
    fake = Faker("fr_FR")
    fake.seed_instance(1)
    report = compose_report(_visit(), "fr", "lab_fr_01", random.Random(1), fake)
    creatinine = next(r for r in report.results if r.name.value == "2160-0")
    assert creatinine.unit is not None and creatinine.unit.text == "µmol/L"
    assert creatinine.value.text == "143"  # 1.62 mg/dL x 88.4
    glucose = next(r for r in report.results if r.name.value == "2345-7")
    assert glucose.value.text == "0,88"
    assert glucose.value.value == "0.88"


def test_flags_follow_reference_ranges() -> None:
    fake = Faker("fr_FR")
    report = compose_report(_visit(), "en", "lab_en_01", random.Random(1), fake)
    flags = {r.name.value: (r.flag.value if r.flag else None) for r in report.results}
    assert flags["718-7"] == "L"
    assert flags["2160-0"] == "H"
    assert flags["2093-3"] == "H"
    assert flags["2823-3"] is None


def test_formatting() -> None:
    assert fmt_number(4.2, 1, "fr") == "4,2"
    assert fmt_number(4.2, 1, "en") == "4.2"
    assert fmt_date(date(2024, 3, 1), "en") == "01 Mar 2024"
    assert fmt_date(date(2024, 3, 1), "fr") == "01/03/2024"
    assert fmt_range("3.5", None) == "> 3.5"
    assert fmt_range(None, None) is None


def test_alternate_specimen_codes_map_to_one_test() -> None:
    assert BY_CODE["2339-0"].loinc == "2345-7"
    codes = [t.loinc for t in CATALOGUE]
    assert len(codes) == len(set(codes))
