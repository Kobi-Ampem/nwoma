"""Read Synthea CSV output into lab visits, streaming row by row to keep memory low."""

import csv
import re
from collections import defaultdict
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from datagen.catalogue import BY_CODE
from datagen.models import SourceLabVisit, SourcePatient, SourceResult

# Synthea appends digits to names to keep them unique ("Josiah310").
_SYNTHEA_SUFFIX = re.compile(r"\d+")


def _clean_name(raw: str) -> str:
    return _SYNTHEA_SUFFIX.sub("", raw).strip()


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def load_lab_visits(csv_dir: Path, min_results: int = 5) -> Iterator[SourceLabVisit]:
    """Yield one visit per encounter that produced at least `min_results` catalogued lab tests."""
    patients = {
        r["Id"]: SourcePatient(
            given=_clean_name(r["FIRST"]),
            family=_clean_name(r["LAST"]),
            birth_date=date.fromisoformat(r["BIRTHDATE"]),
            sex="F" if r["GENDER"] == "F" else "M",
        )
        for r in _rows(csv_dir / "patients.csv")
    }
    providers = {r["Id"]: _clean_name(r["NAME"]) for r in _rows(csv_dir / "providers.csv")}
    organisations = {r["Id"]: r["NAME"] for r in _rows(csv_dir / "organizations.csv")}

    results: dict[str, dict[str, SourceResult]] = defaultdict(dict)
    visit_meta: dict[str, tuple[str, date]] = {}
    for r in _rows(csv_dir / "observations.csv"):
        if r["CATEGORY"] != "laboratory" or r["TYPE"] != "numeric":
            continue
        test = BY_CODE.get(r["CODE"])
        if test is None:
            continue
        # Keyed by canonical code: a blood and a serum variant of one test collapse to one row.
        results[r["ENCOUNTER"]][test.loinc] = SourceResult(
            loinc=test.loinc, value=float(r["VALUE"])
        )
        visit_meta[r["ENCOUNTER"]] = (r["PATIENT"], date.fromisoformat(r["DATE"][:10]))

    wanted = {e for e, rs in results.items() if len(rs) >= min_results}
    for r in _rows(csv_dir / "encounters.csv"):
        encounter = r["Id"]
        if encounter not in wanted:
            continue
        patient_id, collected_on = visit_meta[encounter]
        yield SourceLabVisit(
            visit_id=encounter,
            patient=patients[patient_id],
            collected_on=collected_on,
            clinician=providers.get(r["PROVIDER"], "Unknown"),
            organisation=organisations.get(r["ORGANIZATION"], "Clinical Laboratory"),
            results=list(results[encounter].values()),
        )
