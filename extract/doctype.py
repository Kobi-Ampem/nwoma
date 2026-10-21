"""Tell a lab report from a referral letter before extracting, so each gets its own prompt.

Keyword evidence is enough here: a referral letter talks about referral, diagnoses, medication
and allergies; a lab report is a table of results with units and reference ranges. Words are
matched without case or accents, so OCR damage to one word rarely flips the decision.
"""

import re
from typing import Literal

from normalise.retrieval import fold

DocType = Literal["lab", "referral"]

_REFERRAL = (
    "referral", "referred", "diagnos", "medication", "allerg", "yours sincerely", "dear colleague",
    "adresse", "motif", "antecedent", "traitement", "confrere", "demande d'avis",
)  # fmt: skip
_LAB = (
    "result", "reference", "range", "haematology", "hematology", "biochemistry", "mmol/l",
    "g/dl", "resultat", "valeurs de reference", "hematologie", "biochimie", "normes",
)  # fmt: skip
_UNITS = re.compile(r"\d\s*(mmol/l|µmol/l|umol/l|g/dl|mg/dl|g/l|ui/l|u/l|fl|pg)\b")


def detect_doc_type(text: str) -> DocType:
    t = fold(text)
    referral = sum(t.count(k) for k in _REFERRAL)
    lab = sum(t.count(k) for k in _LAB) + len(_UNITS.findall(t)) // 3
    return "referral" if referral > lab else "lab"
