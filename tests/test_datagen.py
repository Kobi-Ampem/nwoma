import random
from datetime import date

import pytest
from faker import Faker

from datagen.build import sample, split_for
from datagen.catalogue import BY_CODE, CATALOGUE
from datagen.compose import compose_report
from datagen.formatting import fmt_date, fmt_name, fmt_number, fmt_range
from datagen.layouts import LAYOUTS, Layout, layouts_for
from datagen.models import LabReport, SourceLabVisit, SourcePatient, SourceResult
from datagen.render import locate_spans, render_pdf
from ocr.text_layer import pdf_text


def _visit() -> SourceLabVisit:
    return SourceLabVisit(
        visit_id="visit-1",
        patient_id="patient-1",
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


def _report(layout: Layout) -> LabReport:
    fake = Faker("fr_FR")
    fake.seed_instance(1)
    return compose_report(_visit(), layout, random.Random(1), fake)


@pytest.mark.parametrize("name", sorted(LAYOUTS))
def test_every_span_matches_the_pdf_text(name: str) -> None:
    report = _report(LAYOUTS[name])
    text = pdf_text(render_pdf(report))
    spans = locate_spans(text, report)

    for span in spans:
        assert text[span.start : span.end] == span.text

    labels = [s.label for s in spans]
    assert labels.count("TEST_NAME") == len(report.results)
    assert labels.count("TEST_VALUE") == len(report.results)
    assert labels.count("FLAG") == 3
    assert labels.count("TEST_UNIT") == 6  # urine pH prints no unit
    assert {"PATIENT_NAME", "BIRTH_DATE", "SEX", "COLLECTION_DATE", "CLINICIAN"} <= set(labels)


def test_heldout_layouts_use_a_skeleton_training_never_sees() -> None:
    for lang in ("en", "fr"):
        train = layouts_for(lang, "train")
        heldout = layouts_for(lang, "heldout")
        assert len(train) == 6 and len(heldout) == 3
        assert {lay.skeleton for lay in heldout}.isdisjoint({lay.skeleton for lay in train})


def test_split_is_stable_per_patient() -> None:
    assert split_for("patient-1") == split_for("patient-1")
    splits = {split_for(f"p{i}") for i in range(500)}
    assert splits == {"train", "dev", "test", "test_unseen"}


def test_french_report_converts_units_and_uses_decimal_comma() -> None:
    report = _report(LAYOUTS["lab_fr_01"])
    creatinine = next(r for r in report.results if r.name.value == "2160-0")
    assert creatinine.unit is not None and creatinine.unit.text == "µmol/L"
    assert creatinine.value.text == "143"  # 1.62 mg/dL x 88.4
    glucose = next(r for r in report.results if r.name.value == "2345-7")
    assert glucose.value.text == "0,88"
    assert glucose.value.value == "0.88"


def test_flags_follow_reference_ranges() -> None:
    report = _report(LAYOUTS["lab_en_01"])
    flags = {r.name.value: (r.flag.value if r.flag else None) for r in report.results}
    assert flags["718-7"] == "L"
    assert flags["2160-0"] == "H"
    assert flags["2093-3"] == "H"
    assert flags["2823-3"] is None


def test_formatting() -> None:
    assert fmt_number(4.2, 1, "fr") == "4,2"
    assert fmt_number(4.2, 1, "en") == "4.2"
    assert fmt_date(date(2024, 3, 1), "en", "d_mon_y") == "01 Mar 2024"
    assert fmt_date(date(2024, 3, 1), "fr", "d_mon_y") == "01 mars 2024"
    assert fmt_date(date(2024, 3, 1), "fr", "dmy_dot") == "01.03.2024"
    assert fmt_name("Ama", "Mensah", "family_comma_given") == "Mensah, Ama"
    assert fmt_range("3.5", None) == "> 3.5"
    assert fmt_range(None, None) is None


def test_alternate_specimen_codes_map_to_one_test() -> None:
    assert BY_CODE["2339-0"].loinc == "2345-7"
    codes = [t.loinc for t in CATALOGUE]
    assert len(codes) == len(set(codes))


def test_sample_caps_visits_per_patient() -> None:
    # One chronically ill patient with 50 visits, plus 10 patients with one visit each.
    heavy = [_visit().model_copy(update={"visit_id": f"heavy-{i}"}) for i in range(50)]
    light = [
        _visit().model_copy(update={"visit_id": f"light-{i}", "patient_id": f"p-{i}"})
        for i in range(10)
    ]
    chosen = sample(heavy + light, k=100, rng=random.Random(0), per_patient=2)
    assert sum(v.patient_id == "patient-1" for v in chosen) == 2
    assert len(chosen) == 12
    assert len({v.visit_id for v in chosen}) == 12
