"""Referral letters: load a patient's state from Synthea, compose a letter, render it, label it.

A letter is printed as a sequence of sections in the order its layout declares. The template
renders `layout.order` and `locate_referral_spans` walks the text in that same order, anchoring
on each section's heading, so the two cannot disagree about where a field is.
"""

import csv
import hashlib
import random
import re
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import weasyprint
from faker import Faker

from datagen.formatting import fmt_date, fmt_name, fmt_sex
from datagen.layouts import DateStyle, NameStyle, Split
from datagen.models import (
    EntityType,
    Field,
    Lang,
    MedicationRow,
    ReferralLetter,
    SourcePatient,
    SourceReferral,
    Span,
)
from datagen.referral_catalogue import (
    ALLERGIES,
    CONDITIONS,
    FREQUENCIES,
    MEDICATIONS,
    SPECIALTIES,
)
from datagen.render import _FOOTER, SpanNotFoundError, _env

Section = str  # 'header', 'patient', 'reason', 'diagnoses', 'medications', 'allergies', 'sign'
_SYNTHEA_SUFFIX = re.compile(r"\d+")
_MAX_DIAGNOSES, _MAX_MEDICATIONS, _MAX_ALLERGIES = 4, 5, 3


@dataclass(frozen=True)
class ReferralLayout:
    name: str
    lang: Lang
    skeleton: str  # 'letter', 'form' (training) or 'summary' (held out)
    split: Split
    order: tuple[Section, ...]
    headings: dict[str, str]  # section and field labels printed on the letter
    date_style: DateStyle = "dmy_slash"
    name_style: NameStyle = "given_family"
    sex_style: str = "word"
    clinician_prefix: str = "Dr "
    font: str = '"DejaVu Sans", sans-serif'

    @property
    def separator(self) -> str:
        return " : " if self.lang == "fr" else ": "


_EN = {
    "name": "Patient",
    "dob": "Date of birth",
    "sex": "Sex",
    "reason": "Reason for referral",
    "diagnoses": "Diagnoses",
    "medications": "Current medications",
    "allergies": "Allergies",
    "none": "No known allergies",
    "sign": "Yours sincerely,",
    "dear": "Dear colleague,",
    "to": "Referral to",
}
_FR = {
    "name": "Patient(e)",
    "dob": "Date de naissance",
    "sex": "Sexe",
    "reason": "Motif d'adressage",
    "diagnoses": "Antécédents et diagnostics",
    "medications": "Traitement en cours",
    "allergies": "Allergies",
    "none": "Aucune allergie connue",
    "sign": "Bien confraternellement,",
    "dear": "Cher confrère, chère consœur,",
    "to": "Demande d'avis en",
}
_LETTER = ("header", "patient", "reason", "diagnoses", "medications", "allergies", "sign")
_FORM = ("header", "sign", "patient", "allergies", "diagnoses", "medications", "reason")
_SUMMARY = ("header", "patient", "diagnoses", "allergies", "medications", "reason", "sign")

REFERRAL_LAYOUTS: dict[str, ReferralLayout] = {
    lay.name: lay
    for lay in (
        ReferralLayout("ref_en_01", "en", "letter", "train", _LETTER, _EN, date_style="d_mon_y"),
        ReferralLayout(
            "ref_en_02",
            "en",
            "form",
            "train",
            _FORM,
            {**_EN, "name": "Patient name", "medications": "Medication", "sign": "Referred by"},
            name_style="family_upper_given",
            sex_style="letter",
            font='"DejaVu Serif", serif',
        ),
        ReferralLayout(
            "ref_en_03",
            "en",
            "summary",
            "heldout",
            _SUMMARY,
            {**_EN, "reason": "Question for specialist", "sign": "Referring clinician"},
            date_style="iso",
            name_style="family_comma_given",
        ),
        ReferralLayout("ref_fr_01", "fr", "letter", "train", _LETTER, _FR, date_style="d_mon_y"),
        ReferralLayout(
            "ref_fr_02",
            "fr",
            "form",
            "train",
            _FORM,
            {**_FR, "name": "Nom du patient", "medications": "Traitements", "sign": "Adressé par"},
            name_style="family_upper_given",
            sex_style="letter",
            font='"DejaVu Serif", serif',
        ),
        ReferralLayout(
            "ref_fr_03",
            "fr",
            "summary",
            "heldout",
            _SUMMARY,
            {**_FR, "reason": "Question posée", "sign": "Médecin adresseur"},
            date_style="dmy_dot",
            name_style="family_upper_given",
        ),
    )
}


def referral_layouts_for(lang: Lang, split: Split) -> tuple[ReferralLayout, ...]:
    return tuple(
        lay for lay in REFERRAL_LAYOUTS.values() if lay.lang == lang and lay.split == split
    )


def _rows(path: Path) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def _clean(raw: str) -> str:
    return _SYNTHEA_SUFFIX.sub("", raw).strip()


def load_referrals(csv_dir: Path) -> Iterator[SourceReferral]:
    """One referral per patient with at least one catalogued active condition, written at
    their latest visit, by that visit's clinician."""
    conditions: dict[str, list[str]] = defaultdict(list)
    for r in _rows(csv_dir / "conditions.csv"):
        if not r["STOP"] and r["CODE"] in CONDITIONS and r["CODE"] not in conditions[r["PATIENT"]]:
            conditions[r["PATIENT"]].append(r["CODE"])
    medications: dict[str, list[str]] = defaultdict(list)
    for r in _rows(csv_dir / "medications.csv"):
        d = r["DESCRIPTION"]
        if not r["STOP"] and d in MEDICATIONS and d not in medications[r["PATIENT"]]:
            medications[r["PATIENT"]].append(d)
    allergies: dict[str, list[str]] = defaultdict(list)
    for r in _rows(csv_dir / "allergies.csv"):
        d = r["DESCRIPTION"]
        if d in ALLERGIES and d not in allergies[r["PATIENT"]]:
            allergies[r["PATIENT"]].append(d)
    latest: dict[str, dict[str, str]] = {}
    for r in _rows(csv_dir / "encounters.csv"):
        if r["PATIENT"] in conditions and r["START"] > latest.get(r["PATIENT"], {}).get(
            "START", ""
        ):
            latest[r["PATIENT"]] = r
    providers = {r["Id"]: _clean(r["NAME"]) for r in _rows(csv_dir / "providers.csv")}
    organisations = {r["Id"]: r["NAME"] for r in _rows(csv_dir / "organizations.csv")}
    for r in _rows(csv_dir / "patients.csv"):
        pid = r["Id"]
        if pid not in conditions or pid not in latest:
            continue
        visit = latest[pid]
        yield SourceReferral(
            visit_id=visit["Id"],
            patient_id=pid,
            patient=SourcePatient(
                given=_clean(r["FIRST"]),
                family=_clean(r["LAST"]),
                birth_date=date.fromisoformat(r["BIRTHDATE"]),
                sex="F" if r["GENDER"] == "F" else "M",
            ),
            written_on=date.fromisoformat(visit["START"][:10]),
            clinician=providers.get(visit["PROVIDER"], "Unknown"),
            organisation=organisations.get(visit["ORGANIZATION"], "Medical Centre"),
            conditions=conditions[pid],
            medications=medications[pid],
            allergies=allergies[pid],
        )


_REASONS: dict[Lang, tuple[str, ...]] = {
    "en": (
        "Assessment and management of {c}",
        "Further management of {c} despite current treatment",
        "Specialist opinion on {c}",
        "Review of {c} and treatment plan",
    ),
    "fr": (
        "Prise en charge de : {c}",
        "Avis spécialisé concernant : {c}",
        "Réévaluation du traitement pour : {c}",
        "Bilan et suivi de : {c}",
    ),
}


def compose_referral(
    source: SourceReferral, layout: ReferralLayout, rng: random.Random, fake: Faker
) -> ReferralLetter:
    lang = layout.lang
    p = source.patient
    if lang == "fr":  # French letters use French names, like the lab reports
        given = fake.first_name_female() if p.sex == "F" else fake.first_name_male()
        family = fake.last_name()
        clinician = f"{fake.first_name()} {fake.last_name()}"
        clinic = f"Cabinet médical {fake.last_name()}"
    else:
        given, family, clinician, clinic = p.given, p.family, source.clinician, source.organisation

    codes = list(source.conditions)
    rng.shuffle(codes)
    codes = codes[:_MAX_DIAGNOSES]
    primary = CONDITIONS[codes[0]]

    def cond_name(code: str) -> str:
        c = CONDITIONS[code]
        return rng.choice(c.names_fr if lang == "fr" else c.names_en)

    diagnoses = [Field(text=cond_name(code), value=CONDITIONS[code].icd10) for code in codes]
    reason_cond = diagnoses[0].text if lang == "fr" else diagnoses[0].text.lower()
    reason = rng.choice(_REASONS[lang]).format(c=reason_cond)

    meds = list(source.medications)
    rng.shuffle(meds)
    medications = []
    for d in meds[:_MAX_MEDICATIONS]:
        m = MEDICATIONS[d]
        dose = m.dose.replace(".", ",") if lang == "fr" else m.dose
        medications.append(
            MedicationRow(
                name=Field(text=m.name_fr if lang == "fr" else m.name_en, value=m.name_en),
                dose=Field(text=dose, value=m.dose),
                frequency=Field(text=rng.choice(FREQUENCIES[m.frequency][lang]), value=m.frequency),
            )
        )
    allergies = [
        Field(text=ALLERGIES[a][1 if lang == "fr" else 0], value=ALLERGIES[a][0])
        for a in source.allergies[:_MAX_ALLERGIES]
    ]
    doc_id = hashlib.sha256(f"{source.visit_id}|{layout.name}".encode()).hexdigest()[:12]
    return ReferralLetter(
        doc_id=doc_id,
        lang=lang,
        template=layout.name,
        clinic_name=clinic,
        patient_name=Field(
            text=fmt_name(given, family, layout.name_style), value=f"{given} {family}"
        ),
        birth_date=Field(
            text=fmt_date(p.birth_date, lang, layout.date_style), value=p.birth_date.isoformat()
        ),
        sex=Field(text=fmt_sex(p.sex, lang, layout.sex_style), value=p.sex),
        clinician=Field(text=clinician, value=clinician),
        specialty=SPECIALTIES[primary.specialty][lang],
        written=fmt_date(source.written_on, lang, layout.date_style),
        reason=Field(text=reason, value=reason),
        diagnoses=diagnoses,
        medications=medications,
        allergies=allergies,
    )


def render_referral(letter: ReferralLetter) -> bytes:
    layout = REFERRAL_LAYOUTS[letter.template]
    html = _env.get_template(f"referral_{layout.skeleton}.html.j2").render(
        letter=letter,
        layout=layout,
        h=layout.headings,
        footer=_FOOTER[letter.lang],
    )
    pdf: bytes = weasyprint.HTML(string=html).write_pdf()
    return pdf


def _flexible(phrase: str) -> re.Pattern[str]:
    """Match the phrase with any whitespace between its words, and an optional line break after
    '/' or '-', where lines also break: text in a narrow cell wraps."""
    words = [
        re.escape(word).replace("/", r"/\s*").replace(r"\-", r"\-\s*") for word in phrase.split()
    ]
    return re.compile(r"\s+".join(words))


def locate_referral_spans(text: str, letter: ReferralLetter) -> list[Span]:
    """Walk the text in the layout's section order, each field found after its heading."""
    layout = REFERRAL_LAYOUTS[letter.template]
    h = layout.headings
    spans: list[Span] = []
    cursor = 0

    def anchor(heading: str) -> None:
        nonlocal cursor
        m = _flexible(heading).search(text, cursor)
        if m is None:
            raise SpanNotFoundError(f"{letter.doc_id}: heading {heading!r} missing")
        cursor = m.end()

    def find(label: EntityType, f: Field, row: int | None = None) -> None:
        # 'as needed' wraps to 'as\nneeded' in a narrow cell; the span covers it as printed.
        nonlocal cursor
        m = _flexible(f.text).search(text, cursor)
        if m is None:
            raise SpanNotFoundError(f"{letter.doc_id}: {label} {f.text!r} not found")
        spans.append(
            Span(label=label, row=row, text=m.group(), value=f.value, start=m.start(),
                 end=m.end())
        )  # fmt: skip
        cursor = m.end()

    for section in layout.order:
        if section == "patient":
            anchor(h["name"] + layout.separator.rstrip())
            find("PATIENT_NAME", letter.patient_name)
            anchor(h["dob"] + layout.separator.rstrip())
            find("BIRTH_DATE", letter.birth_date)
            anchor(h["sex"] + layout.separator.rstrip())
            find("SEX", letter.sex)
        elif section == "reason":
            anchor(h["reason"])
            find("REASON", letter.reason)
        elif section == "diagnoses":
            anchor(h["diagnoses"])
            for i, d in enumerate(letter.diagnoses):
                find("DIAGNOSIS", d, i)
        elif section == "medications":
            anchor(h["medications"])
            for i, m in enumerate(letter.medications):
                find("MEDICATION", m.name, i)
                find("DOSE", m.dose, i)
                find("FREQUENCY", m.frequency, i)
        elif section == "allergies":
            anchor(h["allergies"])
            for i, a in enumerate(letter.allergies):
                find("ALLERGY", a, i)
        elif section == "sign":
            anchor(h["sign"])
            find("CLINICIAN", letter.clinician)
    # Spans are found section by section; the text order is what models and tests expect.
    return sorted(spans, key=lambda s: s.start)
