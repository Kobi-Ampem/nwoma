"""Lab tests Nwoma prints, keyed by a canonical LOINC code.

Synthea uses the long LOINC description, which no lab prints. Each test here carries the names a
real report would use (several variants per language), the unit printed in each language, and an
approximate adult reference range.

Reference ranges are typical textbook adult values, used only to make synthetic documents
realistic. They are not clinical guidance.

US values (Synthea) are converted to the units French labs report by `fr_factor`.
"""

from dataclasses import dataclass

PANELS: dict[str, dict[str, str]] = {
    "haem": {"en": "Haematology", "fr": "Hématologie"},
    "chem": {"en": "Biochemistry", "fr": "Biochimie"},
    "liver": {"en": "Liver function", "fr": "Bilan hépatique"},
    "lipid": {"en": "Lipid profile", "fr": "Bilan lipidique"},
    "diabetes": {"en": "Diabetes", "fr": "Diabète"},
    "urine": {"en": "Urinalysis", "fr": "Analyse d'urine"},
}


@dataclass(frozen=True)
class LabTest:
    loinc: str
    panel: str
    names_en: tuple[str, ...]
    names_fr: tuple[str, ...]
    unit_en: str
    unit_fr: str
    decimals_en: int
    decimals_fr: int
    low: float | None  # US units
    high: float | None  # US units
    fr_factor: float = 1.0
    alt_codes: tuple[str, ...] = ()  # specimen variants Synthea also emits; same printed test


CATALOGUE: tuple[LabTest, ...] = (
    # Haematology (full blood count)
    LabTest(
        "718-7",
        "haem",
        ("Haemoglobin", "Hemoglobin", "Hb"),
        ("Hémoglobine",),
        "g/dL",
        "g/dL",
        1,
        1,
        12.0,
        17.5,
    ),
    LabTest(
        "4544-3",
        "haem",
        ("Haematocrit", "Hematocrit", "Hct"),
        ("Hématocrite",),
        "%",
        "%",
        1,
        1,
        36.0,
        50.0,
    ),
    LabTest(
        "789-8",
        "haem",
        ("Red blood cells", "RBC", "Erythrocytes"),
        ("Hématies", "Globules rouges"),
        "10⁶/µL",
        "T/L",
        2,
        2,
        4.2,
        5.9,
    ),
    LabTest(
        "6690-2",
        "haem",
        ("White blood cells", "WBC", "Leukocytes"),
        ("Leucocytes", "Globules blancs"),
        "10³/µL",
        "G/L",
        1,
        1,
        4.0,
        11.0,
    ),
    LabTest(
        "777-3", "haem", ("Platelets", "PLT"), ("Plaquettes",), "10³/µL", "G/L", 0, 0, 150.0, 400.0
    ),
    LabTest("787-2", "haem", ("MCV", "Mean cell volume"), ("VGM",), "fL", "fL", 1, 1, 80.0, 100.0),
    LabTest(
        "785-6", "haem", ("MCH", "Mean cell haemoglobin"), ("TCMH",), "pg", "pg", 1, 1, 27.0, 33.0
    ),
    LabTest("786-4", "haem", ("MCHC",), ("CCMH",), "g/dL", "g/dL", 1, 1, 32.0, 36.0),
    LabTest(
        "32623-1", "haem", ("MPV", "Mean platelet volume"), ("VPM",), "fL", "fL", 1, 1, 7.5, 12.5
    ),
    # Biochemistry
    LabTest(
        "2951-2",
        "chem",
        ("Sodium", "Na"),
        ("Sodium", "Natrémie"),
        "mmol/L",
        "mmol/L",
        0,
        0,
        136.0,
        145.0,
        alt_codes=("2947-0",),
    ),
    LabTest(
        "2823-3",
        "chem",
        ("Potassium", "K"),
        ("Potassium", "Kaliémie"),
        "mmol/L",
        "mmol/L",
        1,
        1,
        3.5,
        5.1,
        alt_codes=("6298-4",),
    ),
    LabTest(
        "2075-0",
        "chem",
        ("Chloride", "Cl"),
        ("Chlore", "Chlorures"),
        "mmol/L",
        "mmol/L",
        0,
        0,
        98.0,
        107.0,
        alt_codes=("2069-3",),
    ),
    LabTest(
        "2028-9",
        "chem",
        ("Bicarbonate", "Total CO2"),
        ("Bicarbonates", "CO2 total"),
        "mmol/L",
        "mmol/L",
        0,
        0,
        22.0,
        29.0,
        alt_codes=("20565-8",),
    ),
    LabTest(
        "3094-0",
        "chem",
        ("Urea nitrogen", "BUN"),
        ("Urée",),
        "mg/dL",
        "mmol/L",
        0,
        1,
        7.0,
        20.0,
        fr_factor=0.357,
        alt_codes=("6299-2",),
    ),
    LabTest(
        "2160-0",
        "chem",
        ("Creatinine",),
        ("Créatinine", "Créatininémie"),
        "mg/dL",
        "µmol/L",
        2,
        0,
        0.6,
        1.3,
        fr_factor=88.4,
        alt_codes=("38483-4",),
    ),
    LabTest(
        "33914-3",
        "chem",
        ("eGFR", "Estimated GFR (MDRD)"),
        ("DFG estimé (MDRD)", "DFG"),
        "mL/min/1.73m²",
        "mL/min/1,73m²",
        0,
        0,
        60.0,
        None,
    ),
    LabTest(
        "2345-7",
        "chem",
        ("Glucose",),
        ("Glycémie", "Glucose"),
        "mg/dL",
        "g/L",
        0,
        2,
        70.0,
        99.0,
        fr_factor=0.01,
        alt_codes=("2339-0",),
    ),
    LabTest(
        "17861-6",
        "chem",
        ("Calcium", "Ca"),
        ("Calcium", "Calcémie"),
        "mg/dL",
        "mmol/L",
        1,
        2,
        8.5,
        10.2,
        fr_factor=0.2495,
        alt_codes=("49765-1",),
    ),
    # Liver
    LabTest(
        "1751-7",
        "liver",
        ("Albumin",),
        ("Albumine",),
        "g/dL",
        "g/L",
        1,
        0,
        3.5,
        5.0,
        fr_factor=10.0,
    ),
    LabTest(
        "2885-2",
        "liver",
        ("Total protein",),
        ("Protéines totales",),
        "g/dL",
        "g/L",
        1,
        0,
        6.0,
        8.3,
        fr_factor=10.0,
    ),
    LabTest(
        "1975-2",
        "liver",
        ("Total bilirubin", "Bilirubin"),
        ("Bilirubine totale",),
        "mg/dL",
        "µmol/L",
        1,
        0,
        0.1,
        1.2,
        fr_factor=17.1,
    ),
    LabTest(
        "6768-6",
        "liver",
        ("Alkaline phosphatase", "ALP"),
        ("Phosphatases alcalines", "PAL"),
        "U/L",
        "UI/L",
        0,
        0,
        44.0,
        147.0,
    ),
    LabTest("1920-8", "liver", ("AST",), ("ASAT",), "U/L", "UI/L", 0, 0, 10.0, 40.0),
    LabTest("1742-6", "liver", ("ALT",), ("ALAT",), "U/L", "UI/L", 0, 0, 7.0, 56.0),
    # Lipids
    LabTest(
        "2093-3",
        "lipid",
        ("Total cholesterol", "Cholesterol"),
        ("Cholestérol total",),
        "mg/dL",
        "g/L",
        0,
        2,
        None,
        200.0,
        fr_factor=0.01,
    ),
    LabTest(
        "2085-9",
        "lipid",
        ("HDL cholesterol", "HDL-C"),
        ("HDL-cholestérol",),
        "mg/dL",
        "g/L",
        0,
        2,
        40.0,
        None,
        fr_factor=0.01,
    ),
    LabTest(
        "18262-6",
        "lipid",
        ("LDL cholesterol", "LDL-C"),
        ("LDL-cholestérol",),
        "mg/dL",
        "g/L",
        0,
        2,
        None,
        100.0,
        fr_factor=0.01,
    ),
    LabTest(
        "2571-8",
        "lipid",
        ("Triglycerides",),
        ("Triglycérides",),
        "mg/dL",
        "g/L",
        0,
        2,
        None,
        150.0,
        fr_factor=0.01,
    ),
    # Diabetes
    LabTest(
        "4548-4",
        "diabetes",
        ("HbA1c", "Haemoglobin A1c"),
        ("HbA1c", "Hémoglobine glyquée"),
        "%",
        "%",
        1,
        1,
        4.0,
        5.6,
    ),
    LabTest(
        "14959-1",
        "diabetes",
        ("Urine albumin/creatinine ratio", "ACR"),
        ("Rapport albumine/créatinine urinaire",),
        "mg/g",
        "mg/g",
        1,
        1,
        None,
        30.0,
    ),
    # Urinalysis (dipstick)
    LabTest(
        "5811-5", "urine", ("Specific gravity",), ("Densité urinaire",), "", "", 3, 3, 1.005, 1.030
    ),
    LabTest("5803-2", "urine", ("Urine pH", "pH"), ("pH urinaire",), "", "", 1, 1, 4.5, 8.0),
    LabTest(
        "5792-7",
        "urine",
        ("Urine glucose",),
        ("Glucose urinaire",),
        "mg/dL",
        "mg/dL",
        0,
        0,
        None,
        None,
    ),
    LabTest(
        "5804-0",
        "urine",
        ("Urine protein",),
        ("Protéines urinaires",),
        "mg/dL",
        "mg/dL",
        0,
        0,
        None,
        None,
    ),
    LabTest(
        "5797-6",
        "urine",
        ("Urine ketones",),
        ("Corps cétoniques urinaires",),
        "mg/dL",
        "mg/dL",
        0,
        0,
        None,
        None,
    ),
)

BY_CODE: dict[str, LabTest] = {}
for _test in CATALOGUE:
    for _code in (_test.loinc, *_test.alt_codes):
        BY_CODE[_code] = _test

PANEL_ORDER: tuple[str, ...] = tuple(PANELS)
