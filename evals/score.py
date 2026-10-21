"""Score an extraction against a labelled document, field by field.

Decisions an interviewer may probe:
- A wrong value counts as both a false positive (something wrong was returned) and a false
  negative (the truth was missed), the usual rule in slot filling.
- On scans, fields OCR destroyed are left out of the truth: no extractor can read what is not
  in the text. A value returned for such a field still counts as a false positive.
- Test names and units are compared with what was printed, since mapping names to LOINC codes
  and converting units are separate tasks. Everything else is compared with the normalised truth.
- Predicted rows are matched to true rows by test name similarity, so a skipped row costs only
  that row and does not shift every row after it.
"""

import re
from collections import Counter
from collections.abc import Callable
from difflib import SequenceMatcher

from datagen.models import EntityType, Field, LabeledDoc, LabReport, ReferralLetter
from extract.schema import ExtractedResult, Extraction
from normalise.fields import (
    norm_clinician,
    norm_date,
    norm_flag,
    norm_name,
    norm_number,
    norm_range,
    norm_sex,
)

HEADER: list[EntityType] = ["PATIENT_NAME", "BIRTH_DATE", "SEX", "COLLECTION_DATE", "CLINICIAN"]
ROW: list[EntityType] = ["TEST_NAME", "TEST_VALUE", "TEST_UNIT", "REF_RANGE", "FLAG"]
# Referral letters: header fields, medication rows, and lists compared as sets.
REFERRAL_HEADER: list[EntityType] = ["PATIENT_NAME", "BIRTH_DATE", "SEX", "CLINICIAN", "REASON"]
MEDICATION_ROW: list[EntityType] = ["MEDICATION", "DOSE", "FREQUENCY"]
REFERRAL_LISTS: list[EntityType] = ["DIAGNOSIS", "ALLERGY"]
ALL_LABELS: list[EntityType] = list(
    dict.fromkeys(HEADER + ROW + REFERRAL_HEADER + MEDICATION_ROW + REFERRAL_LISTS)
)
_ROW_MATCH_MIN = 0.6
# Fields besides the name that identify a row; two of three agreeing (0.67) is a match.
_ROW_EVIDENCE: list[EntityType] = ["TEST_VALUE", "TEST_UNIT", "REF_RANGE"]

Fields = dict[EntityType, str]


def _canon(label: EntityType, text: str) -> str:
    """The form two values are compared in."""
    if label == "TEST_VALUE":
        try:
            return repr(float(text))
        except ValueError:
            return text
    return " ".join(text.split()).casefold()


def gold(doc: LabeledDoc) -> tuple[Fields, list[Fields]]:
    """The truth for every field of a lab report that survived into the document's text."""
    if not isinstance(doc.report, LabReport):
        raise TypeError("gold() scores lab reports; see _score_referral")
    header: Fields = {}
    rows: list[Fields] = [{} for _ in doc.report.results]
    for span in doc.spans:
        if span.row is None:
            header[span.label] = span.value
            continue
        printed = doc.report.results[span.row]
        if span.label == "TEST_NAME":
            rows[span.row][span.label] = printed.name.text
        elif span.label == "TEST_UNIT" and printed.unit is not None:
            rows[span.row][span.label] = printed.unit.text
        else:
            rows[span.row][span.label] = span.value
    return header, rows


_HEADER_NORM: dict[EntityType, Callable[[str], str]] = {
    "PATIENT_NAME": norm_name,
    "BIRTH_DATE": norm_date,
    "SEX": norm_sex,
    "COLLECTION_DATE": norm_date,
    "CLINICIAN": norm_clinician,
}


def predicted(ext: Extraction) -> tuple[Fields, list[Fields]]:
    raw = {
        "PATIENT_NAME": ext.patient_name,
        "BIRTH_DATE": ext.birth_date,
        "SEX": ext.sex,
        "COLLECTION_DATE": ext.collection_date,
        "CLINICIAN": ext.clinician,
    }
    header: Fields = {
        label: _HEADER_NORM[label](raw[label] or "") for label in HEADER if raw[label]
    }
    return header, [_row(r) for r in ext.results]


def _row(r: ExtractedResult) -> Fields:
    row: Fields = {}
    if r.test_name:  # an empty string means "not found", not a wrong answer
        row["TEST_NAME"] = r.test_name
    if r.value:
        row["TEST_VALUE"] = norm_number(r.value)
    if r.unit:
        row["TEST_UNIT"] = r.unit
    if r.ref_range:
        row["REF_RANGE"] = norm_range(r.ref_range)
    if r.flag:
        row["FLAG"] = norm_flag(r.flag)
    return row


def _compare(truth: Fields, guess: Fields, labels: list[EntityType], counts: Counter[str]) -> None:
    for label in labels:
        t, g = truth.get(label), guess.get(label)
        if t is not None and g is not None and _canon(label, t) == _canon(label, g):
            counts[f"{label}/tp"] += 1
            continue
        if g is not None:
            counts[f"{label}/fp"] += 1
        if t is not None:
            counts[f"{label}/fn"] += 1


def _match_rows(
    truth: list[Fields],
    guess: list[Fields],
    names: list[str],
    name_label: EntityType = "TEST_NAME",
    evidence: list[EntityType] = _ROW_EVIDENCE,
) -> list[tuple[int | None, int | None]]:
    """Pair true and predicted rows greedily, by test name similarity or by agreement of the
    row's other fields, whichever is stronger. Short names like 'Cl' misread as 'ct' have no name
    similarity left, but a row whose value, unit and range all agree is still the same row."""

    def strength(t: Fields, g: Fields, name: str) -> float:
        by_name = SequenceMatcher(None, name.casefold(), g.get(name_label, "").casefold()).ratio()
        agree = sum(
            label in t and label in g and _canon(label, t[label]) == _canon(label, g[label])
            for label in evidence
        )
        return max(by_name, agree / len(evidence))

    pairs = sorted(
        (
            (strength(truth[i], g, names[i]), i, j)
            for i in range(len(truth))
            for j, g in enumerate(guess)
        ),
        reverse=True,
    )
    used_t: set[int] = set()
    used_g: set[int] = set()
    matched: list[tuple[int | None, int | None]] = []
    for ratio, i, j in pairs:
        if ratio < _ROW_MATCH_MIN:
            break
        if i not in used_t and j not in used_g:
            used_t.add(i)
            used_g.add(j)
            matched.append((i, j))
    matched += [(i, None) for i in range(len(truth)) if i not in used_t]
    matched += [(None, j) for j in range(len(guess)) if j not in used_g]
    return matched


def score_doc(doc: LabeledDoc, ext: Extraction) -> Counter[str]:
    """Counts keyed '<LABEL>/<tp|fp|fn>'."""
    if isinstance(doc.report, ReferralLetter):
        return _score_referral(doc, doc.report, ext)
    counts: Counter[str] = Counter()
    true_header, true_rows = gold(doc)
    guess_header, guess_rows = predicted(ext)
    _compare(true_header, guess_header, HEADER, counts)
    names = [r.name.text for r in doc.report.results]
    for i, j in _match_rows(true_rows, guess_rows, names):
        _compare(
            true_rows[i] if i is not None else {},
            guess_rows[j] if j is not None else {},
            ROW,
            counts,
        )
    return counts


def prf(counts: Counter[str], labels: list[EntityType] | None = None) -> tuple[float, float, float]:
    """Micro precision, recall and F1 over the given labels (all by default)."""
    labels = labels or ALL_LABELS
    tp = sum(counts[f"{label}/tp"] for label in labels)
    fp = sum(counts[f"{label}/fp"] for label in labels)
    fn = sum(counts[f"{label}/fn"] for label in labels)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def all_correct(counts: Counter[str]) -> bool:
    return not any(v for k, v in counts.items() if k.endswith(("/fp", "/fn")))


def _norm_dose(text: str) -> str:
    """'2,5 mg' -> '2.5 mg': the stored dose value uses a dot decimal."""
    return " ".join(re.sub(r"(\d),(\d)", r"\1.\2", text).split())


def _score_referral(doc: LabeledDoc, letter: ReferralLetter, ext: Extraction) -> Counter[str]:
    """Header fields as for lab reports, medication rows matched by name, and diagnoses and
    allergies compared as sets of printed text (mapping diagnoses to ICD-10 is scored apart)."""
    counts: Counter[str] = Counter()
    survived = {(s.label, s.row) for s in doc.spans}
    truth: Fields = {s.label: s.value for s in doc.spans if s.label in REFERRAL_HEADER}
    guess_raw: dict[EntityType, str | None] = {
        "PATIENT_NAME": ext.patient_name,
        "BIRTH_DATE": ext.birth_date,
        "SEX": ext.sex,
        "CLINICIAN": ext.clinician,
        "REASON": ext.reason,
    }
    norms: dict[EntityType, Callable[[str], str]] = {**_HEADER_NORM, "REASON": str.strip}
    guess: Fields = {label: norms[label](v) for label in REFERRAL_HEADER if (v := guess_raw[label])}
    _compare(truth, guess, REFERRAL_HEADER, counts)

    true_meds: list[Fields] = []
    for i, m in enumerate(letter.medications):
        row: Fields = {}
        fields: list[tuple[EntityType, str]] = [
            ("MEDICATION", m.name.text),
            ("DOSE", m.dose.value),
            ("FREQUENCY", m.frequency.text),
        ]
        for label, value in fields:
            if (label, i) in survived:
                row[label] = value
        true_meds.append(row)
    guess_meds: list[Fields] = []
    for gm in ext.medications:
        row = {"MEDICATION": gm.name} if gm.name else {}
        if gm.dose:
            row["DOSE"] = _norm_dose(gm.dose)
        if gm.frequency:
            row["FREQUENCY"] = gm.frequency
        guess_meds.append(row)
    names = [m.name.text for m in letter.medications]
    for ti, gi in _match_rows(true_meds, guess_meds, names, "MEDICATION", ["DOSE", "FREQUENCY"]):
        t = true_meds[ti] if ti is not None else {}
        g = guess_meds[gi] if gi is not None else {}
        _compare(t, g, MEDICATION_ROW, counts)

    lists: list[tuple[EntityType, list[Field], list[str]]] = [
        ("DIAGNOSIS", letter.diagnoses, ext.diagnoses),
        ("ALLERGY", letter.allergies, ext.allergies),
    ]
    for label, printed, guessed in lists:
        want = Counter(
            _canon(label, f.text) for i, f in enumerate(printed) if (label, i) in survived
        )
        got = Counter(_canon(label, g) for g in guessed if g)
        tp = sum((want & got).values())
        counts[f"{label}/tp"] += tp
        counts[f"{label}/fp"] += sum(got.values()) - tp
        counts[f"{label}/fn"] += sum(want.values()) - tp
    return counts
