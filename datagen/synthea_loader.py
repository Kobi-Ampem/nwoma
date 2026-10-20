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

    # (priority, result) per encounter and canonical test. Synthea often records a blood and a
    # serum variant of the same test in one encounter; the canonical (serum) code wins, then the
    # first row seen, so the printed value never depends on CSV row order.
    results: dict[str, dict[str, tuple[int, SourceResult]]] = defaultdict(dict)
    patient_of: dict[str, str] = {}
    for r in _rows(csv_dir / "observations.csv"):
        if r["CATEGORY"] != "laboratory" or r["TYPE"] != "numeric":
            continue
        test = BY_CODE.get(r["CODE"])
        if test is None:
            continue
        priority = 0 if r["CODE"] == test.loinc else 1
        current = results[r["ENCOUNTER"]].get(test.loinc)
        if current is None or priority < current[0]:
            result = SourceResult(loinc=test.loinc, value=float(r["VALUE"]))
            results[r["ENCOUNTER"]][test.loinc] = (priority, result)
        patient_of[r["ENCOUNTER"]] = r["PATIENT"]

    wanted = {e for e, rs in results.items() if len(rs) >= min_results}
    for r in _rows(csv_dir / "encounters.csv"):
        encounter = r["Id"]
        if encounter not in wanted:
            continue
        patient_id = patient_of[encounter]
        yield SourceLabVisit(
            visit_id=encounter,
            patient_id=patient_id,
            patient=patients[patient_id],
            # The encounter's own start date: observations within one visit can span midnight.
            collected_on=date.fromisoformat(r["START"][:10]),
            clinician=providers.get(r["PROVIDER"], "Unknown"),
            organisation=organisations.get(r["ORGANIZATION"], "Clinical Laboratory"),
            results=[result for _, result in results[encounter].values()],
        )
