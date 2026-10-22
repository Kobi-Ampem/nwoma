"""Check an extraction for things that cannot be right, whichever extractor produced it.

These checks need no model and no confidence score. They catch the errors confidence misses:
the NER model tags an unfamiliar flag 'not a flag' with high confidence (ADR 0002), but a value
of 1.62 against a range of 0.60 - 1.30 says a flag is missing. Each issue names the field, so the
cascade and the review screen can point at it.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from extract.doctype import DocType
from extract.schema import Extraction
from normalise.fields import norm_date, norm_flag, parse_number, parse_range

_DOSE = re.compile(r"\d")


@dataclass(frozen=True)
class Issue:
    field: str  # e.g. 'birth_date', 'results[3].flag', 'medications[0].dose'
    kind: str  # short machine-readable reason
    message: str


def _iso(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(norm_date(text))
    except ValueError:
        return None


def validate(ext: Extraction, doc_type: DocType) -> list[Issue]:
    issues: list[Issue] = []

    def add(field: str, kind: str, message: str) -> None:
        issues.append(Issue(field, kind, message))

    required = ["patient_name", "birth_date"]
    required += ["collection_date"] if doc_type == "lab" else ["clinician", "reason"]
    for name in required:
        if not getattr(ext, name):
            add(name, "missing", f"{name.replace('_', ' ')} not found")
    birth = _iso(ext.birth_date)
    if ext.birth_date and birth is None:
        add("birth_date", "unreadable_date", f"'{ext.birth_date}' is not a date")
    if doc_type == "lab":
        collected = _iso(ext.collection_date)
        if ext.collection_date and collected is None:
            add("collection_date", "unreadable_date", f"'{ext.collection_date}' is not a date")
        if birth and collected and collected < birth:
            add("collection_date", "before_birth", "sample collected before the patient was born")
        _check_results(ext, add)
    else:
        if not ext.diagnoses:
            add("diagnoses", "missing", "no diagnosis found")
        for i, m in enumerate(ext.medications):
            if not m.dose or not _DOSE.search(m.dose):
                add(f"medications[{i}].dose", "missing", f"no dose for {m.name or 'a medication'}")
    return issues


def _check_results(ext: Extraction, add: Callable[[str, str, str], None]) -> None:
    if not ext.results:
        add("results", "missing", "no test results found")
    names = [r.test_name.casefold() for r in ext.results if r.test_name]
    for i, r in enumerate(ext.results):
        where = f"results[{i}]"
        if not r.test_name:
            add(f"{where}.test_name", "missing", "result row without a test name")
        if names.count(r.test_name.casefold()) > 1 and r.test_name:
            add(f"{where}.test_name", "duplicate", f"'{r.test_name}' appears more than once")
        if not r.value:
            add(f"{where}.value", "missing", f"no value for {r.test_name or 'a test'}")
            continue
        v = parse_number(r.value)
        if v is None:
            add(f"{where}.value", "not_a_number", f"value '{r.value}' is not a number")
            continue
        flag = norm_flag(r.flag) if r.flag else None
        if r.flag and flag not in ("H", "L"):
            add(f"{where}.flag", "unknown_flag", f"flag '{r.flag}' is not high or low")
            continue
        if not r.ref_range:
            continue
        bounds = parse_range(r.ref_range)
        if bounds is None:
            add(f"{where}.ref_range", "unreadable_range", f"range '{r.ref_range}' unreadable")
            continue
        low, high = bounds
        expected = None
        if high is not None and v > high:
            expected = "H"
        elif low is not None and v < low:
            expected = "L"
        if expected != flag:
            if expected and not flag:
                msg = f"{r.test_name} {r.value} is outside {r.ref_range} but has no flag"
            elif flag and not expected:
                msg = f"{r.test_name} {r.value} is within {r.ref_range} but flagged {r.flag}"
            else:
                msg = f"{r.test_name} {r.value} flagged {r.flag}, expected {expected}"
            add(f"{where}.flag", "flag_mismatch", msg)
