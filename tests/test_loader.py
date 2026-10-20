from datetime import date
from pathlib import Path

from datagen.synthea_loader import load_lab_visits

_OBS_HEADER = "DATE,PATIENT,ENCOUNTER,CATEGORY,CODE,DESCRIPTION,VALUE,UNITS,TYPE\n"


def _write_synthea(tmp: Path, observations: list[str]) -> None:
    (tmp / "patients.csv").write_text(
        "Id,BIRTHDATE,FIRST,LAST,GENDER\np1,1980-01-02,Ama310,Mensah604,F\n"
    )
    (tmp / "providers.csv").write_text("Id,NAME\npr1,Kwame12 Boateng7\n")
    (tmp / "organizations.csv").write_text("Id,NAME\no1,Kumasi Lab\n")
    (tmp / "encounters.csv").write_text(
        "Id,START,PATIENT,ORGANIZATION,PROVIDER\ne1,2024-03-21T23:50:00Z,p1,o1,pr1\n"
    )
    (tmp / "observations.csv").write_text(_OBS_HEADER + "".join(observations))


def _obs(code: str, value: str, day: str = "2024-03-21") -> str:
    return f"{day}T23:55:00Z,p1,e1,laboratory,{code},x,{value},u,numeric\n"


def test_canonical_code_wins_over_specimen_variant_regardless_of_row_order(tmp_path: Path) -> None:
    rows = [_obs("2339-0", "90"), _obs("2345-7", "100")]  # blood glucose first, serum second
    rows += [_obs(code, "1") for code in ("718-7", "2823-3", "2951-2", "2075-0")]
    _write_synthea(tmp_path, rows)
    (visit,) = load_lab_visits(tmp_path)
    glucose = next(r for r in visit.results if r.loinc == "2345-7")
    assert glucose.value == 100
    assert len(visit.results) == 5


def test_visit_date_comes_from_the_encounter_and_names_lose_synthea_digits(tmp_path: Path) -> None:
    rows = [_obs(code, "1", day="2024-03-22") for code in ("718-7", "2823-3", "2951-2", "2075-0")]
    rows.append(_obs("2345-7", "1"))
    _write_synthea(tmp_path, rows)
    (visit,) = load_lab_visits(tmp_path)
    assert visit.collected_on == date(2024, 3, 21)
    assert (visit.patient.given, visit.patient.family) == ("Ama", "Mensah")
    assert visit.clinician == "Kwame Boateng"


def test_visits_below_the_minimum_are_skipped(tmp_path: Path) -> None:
    _write_synthea(tmp_path, [_obs("718-7", "1"), _obs("2823-3", "1")])
    assert list(load_lab_visits(tmp_path)) == []
