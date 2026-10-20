"""The 12 document layouts: 4 HTML skeletons, each layout varying wording, order and formats.

Layouts marked `heldout` use the `list` skeleton, which no training layout uses, so the
unseen-layout test set measures generalisation to a new structure, not just new wording.
"""

from dataclasses import dataclass
from typing import Literal

from datagen.models import Lang

Column = Literal["name", "value", "unit", "ref", "flag"]
DateStyle = Literal["d_mon_y", "dmy_slash", "dmy_dot", "iso"]
NameStyle = Literal["given_family", "family_upper_given", "family_comma_given"]
FlagStyle = Literal["letter", "word", "arrow"]
Split = Literal["train", "heldout"]

STANDARD: tuple[Column, ...] = ("name", "value", "unit", "ref", "flag")


@dataclass(frozen=True)
class Layout:
    name: str
    lang: Lang
    skeleton: str
    split: Split
    title: str
    # Header label printed before each field. The span locator anchors on label + separator.
    labels: dict[str, str]
    headings: dict[Column, str]
    columns: tuple[Column, ...] = STANDARD
    date_style: DateStyle = "dmy_slash"
    name_style: NameStyle = "given_family"
    sex_style: Literal["word", "letter"] = "word"
    flag_style: FlagStyle = "letter"
    clinician_prefix: str = "Dr "
    ref_brackets: bool = False
    font: str = '"DejaVu Sans", sans-serif'

    @property
    def separator(self) -> str:
        # French typography puts a space before the colon.
        return " : " if self.lang == "fr" else ": "

    def anchor(self, entity: str) -> str:
        return self.labels[entity] + self.separator.rstrip()


def _labels(name: str, birth: str, sex: str, collected: str, clinician: str) -> dict[str, str]:
    return {
        "PATIENT_NAME": name,
        "BIRTH_DATE": birth,
        "SEX": sex,
        "COLLECTION_DATE": collected,
        "CLINICIAN": clinician,
    }


_EN_HEAD: dict[Column, str] = {
    "name": "Test",
    "value": "Result",
    "unit": "Units",
    "ref": "Reference range",
    "flag": "Flag",
}
_FR_HEAD: dict[Column, str] = {
    "name": "Analyse",
    "value": "Résultat",
    "unit": "Unité",
    "ref": "Valeurs de référence",
    "flag": "",
}

LAYOUTS: dict[str, Layout] = {
    layout.name: layout
    for layout in (
        # English, training layouts
        Layout(
            "lab_en_01",
            "en",
            "table",
            "train",
            "Laboratory report",
            _labels("Patient name", "Date of birth", "Sex", "Collected", "Requesting clinician"),
            _EN_HEAD,
            date_style="d_mon_y",
        ),
        Layout(
            "lab_en_02",
            "en",
            "boxed",
            "train",
            "Pathology results",
            _labels("Name", "DOB", "Gender", "Sample date", "Ordered by"),
            _EN_HEAD,
            name_style="family_upper_given",
            sex_style="letter",
            font='"DejaVu Serif", serif',
        ),
        Layout(
            "lab_en_03",
            "en",
            "sidebar",
            "train",
            "Clinical chemistry and haematology",
            _labels("Patient", "Born", "Sex", "Collection date", "Referring doctor"),
            _EN_HEAD,
            date_style="dmy_dot",
            flag_style="word",
            clinician_prefix="Dr. ",
        ),
        Layout(
            "lab_en_04",
            "en",
            "table",
            "train",
            "Test results",
            _labels("Patient", "D.O.B.", "Sex", "Date collected", "Physician"),
            {**_EN_HEAD, "ref": "Normal range"},
            columns=("name", "value", "flag", "unit", "ref"),
            date_style="iso",
            name_style="family_comma_given",
            flag_style="arrow",
            font='"DejaVu Sans Mono", monospace',
        ),
        # English, held out
        Layout(
            "lab_en_05",
            "en",
            "list",
            "heldout",
            "Laboratory findings",
            _labels("Full name", "Birth date", "Sex", "Specimen received", "Clinician"),
            _EN_HEAD,
            date_style="d_mon_y",
            flag_style="arrow",
            ref_brackets=True,
        ),
        Layout(
            "lab_en_06",
            "en",
            "list",
            "heldout",
            "Results summary",
            _labels("Name of patient", "Date of birth", "Gender", "Sampled on", "Requested by"),
            _EN_HEAD,
            columns=("name", "value", "unit", "flag", "ref"),
            date_style="dmy_dot",
            name_style="family_upper_given",
            sex_style="letter",
            ref_brackets=True,
            font='"DejaVu Serif", serif',
        ),
        # French, training layouts
        Layout(
            "lab_fr_01",
            "fr",
            "boxed",
            "train",
            "Compte rendu d'analyses de biologie médicale",
            _labels(
                "Nom du patient", "Date de naissance", "Sexe", "Date de prélèvement", "Prescripteur"
            ),
            _FR_HEAD,
            name_style="family_upper_given",
            font='"DejaVu Serif", serif',
        ),
        Layout(
            "lab_fr_02",
            "fr",
            "table",
            "train",
            "Résultats d'analyses",
            _labels("Patient", "Né(e) le", "Sexe", "Prélevé le", "Médecin prescripteur"),
            _FR_HEAD,
            date_style="d_mon_y",
            name_style="family_upper_given",
        ),
        Layout(
            "lab_fr_03",
            "fr",
            "sidebar",
            "train",
            "Laboratoire de biologie médicale",
            _labels("Nom", "Date de naissance", "Sexe", "Date du prélèvement", "Demandé par"),
            _FR_HEAD,
            name_style="family_comma_given",
            sex_style="letter",
            flag_style="word",
        ),
        Layout(
            "lab_fr_04",
            "fr",
            "table",
            "train",
            "Bilan biologique",
            _labels("Identité", "Né(e) le", "Sexe", "Prélèvement du", "Prescripteur"),
            {**_FR_HEAD, "ref": "Normes"},
            columns=("name", "value", "flag", "unit", "ref"),
            date_style="dmy_dot",
            name_style="family_upper_given",
            flag_style="arrow",
            font='"DejaVu Sans Mono", monospace',
        ),
        # French, held out
        Layout(
            "lab_fr_05",
            "fr",
            "list",
            "heldout",
            "Résultats de biologie",
            _labels("Patient(e)", "Date de naissance", "Sexe", "Échantillon prélevé le", "Médecin"),
            _FR_HEAD,
            name_style="family_upper_given",
            ref_brackets=True,
            font='"DejaVu Serif", serif',
        ),
        Layout(
            "lab_fr_06",
            "fr",
            "list",
            "heldout",
            "Synthèse des analyses",
            _labels("Nom et prénom", "Naissance", "Genre", "Date d'examen", "Adressé par"),
            _FR_HEAD,
            columns=("name", "value", "unit", "flag", "ref"),
            date_style="iso",
            flag_style="word",
            ref_brackets=True,
        ),
    )
}


def layouts_for(lang: Lang, split: Split) -> tuple[Layout, ...]:
    return tuple(lay for lay in LAYOUTS.values() if lay.lang == lang and lay.split == split)
