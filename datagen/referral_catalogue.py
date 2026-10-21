"""What a referral letter can mention: conditions, medications, allergies, keyed by Synthea codes.

Each condition carries its ICD-10-CM code (checked against the CMS FY2027 file by
`tests/test_referral.py` when the file is present) and the wording a letter would use in each
language. Social findings Synthea records ('Full-time employment', 'Stress') are left out: they
are not diagnoses a referral lists.

Frequencies are typical for the drug, used only to make letters realistic. Not clinical guidance.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Condition:
    icd10: str
    names_en: tuple[str, ...]
    names_fr: tuple[str, ...]
    specialty: str  # key into SPECIALTIES


@dataclass(frozen=True)
class Medication:
    name_en: str
    name_fr: str
    dose: str  # as Synthea gives it, e.g. '10 mg'; French prints the same with a comma decimal
    frequency: str  # key into FREQUENCIES


SPECIALTIES: dict[str, dict[str, str]] = {
    "endo": {"en": "endocrinology", "fr": "endocrinologie"},
    "cardio": {"en": "cardiology", "fr": "cardiologie"},
    "nephro": {"en": "nephrology", "fr": "néphrologie"},
    "rheum": {"en": "rheumatology", "fr": "rhumatologie"},
    "neuro": {"en": "neurology", "fr": "neurologie"},
    "resp": {"en": "respiratory medicine", "fr": "pneumologie"},
    "haem": {"en": "haematology", "fr": "hématologie"},
    "ent": {"en": "ENT", "fr": "ORL"},
    "uro": {"en": "urology", "fr": "urologie"},
    "pain": {"en": "the pain clinic", "fr": "consultation douleur"},
    "sleep": {"en": "the sleep clinic", "fr": "consultation du sommeil"},
    "dental": {"en": "dental surgery", "fr": "chirurgie dentaire"},
}

CONDITIONS: dict[str, Condition] = {
    "15777000": Condition("R73.03", ("Prediabetes",), ("Prédiabète",), "endo"),
    "44054006": Condition(
        "E11.9",
        ("Type 2 diabetes mellitus", "Type 2 diabetes"),
        ("Diabète de type 2", "Diabète sucré de type 2"),
        "endo",
    ),
    "127013003": Condition(
        "E11.21",
        ("Diabetic nephropathy", "Type 2 diabetes with nephropathy"),
        ("Néphropathie diabétique",),
        "nephro",
    ),
    "90781000119102": Condition(
        "E11.29",
        ("Microalbuminuria due to type 2 diabetes",),
        ("Microalbuminurie liée au diabète de type 2",),
        "nephro",
    ),
    "368581000119106": Condition(
        "E11.40",
        ("Diabetic neuropathy", "Neuropathy due to type 2 diabetes"),
        ("Neuropathie diabétique",),
        "neuro",
    ),
    "422034002": Condition(
        "E11.319",
        ("Diabetic retinopathy",),
        ("Rétinopathie diabétique",),
        "endo",
    ),
    "80394007": Condition("R73.9", ("Hyperglycaemia", "Hyperglycemia"), ("Hyperglycémie",), "endo"),
    "162864005": Condition("E66.9", ("Obesity",), ("Obésité",), "endo"),
    "237602007": Condition("E88.810", ("Metabolic syndrome",), ("Syndrome métabolique",), "endo"),
    "59621000": Condition(
        "I10",
        ("Essential hypertension", "Hypertension"),
        ("Hypertension artérielle essentielle", "HTA essentielle"),
        "cardio",
    ),
    "414545008": Condition(
        "I25.9",
        ("Ischaemic heart disease", "Ischemic heart disease"),
        ("Cardiopathie ischémique",),
        "cardio",
    ),
    "49436004": Condition(
        "I48.91",
        ("Atrial fibrillation",),
        ("Fibrillation atriale", "Fibrillation auriculaire"),
        "cardio",
    ),
    "60573004": Condition(
        "I35.0",
        ("Aortic valve stenosis", "Aortic stenosis"),
        ("Rétrécissement aortique",),
        "cardio",
    ),
    "55822004": Condition(
        "E78.5", ("Hyperlipidaemia", "Hyperlipidemia"), ("Hyperlipidémie",), "cardio"
    ),
    "302870006": Condition(
        "E78.1", ("Hypertriglyceridaemia",), ("Hypertriglycéridémie",), "cardio"
    ),
    "431855005": Condition(
        "N18.1",
        ("Chronic kidney disease stage 1", "CKD stage 1"),
        ("Maladie rénale chronique stade 1",),
        "nephro",
    ),
    "431856006": Condition(
        "N18.2",
        ("Chronic kidney disease stage 2", "CKD stage 2"),
        ("Maladie rénale chronique stade 2",),
        "nephro",
    ),
    "433144002": Condition(
        "N18.30",
        ("Chronic kidney disease stage 3", "CKD stage 3"),
        ("Insuffisance rénale chronique stade 3",),
        "nephro",
    ),
    "431857002": Condition(
        "N18.4",
        ("Chronic kidney disease stage 4", "CKD stage 4"),
        ("Insuffisance rénale chronique stade 4",),
        "nephro",
    ),
    "197927001": Condition(
        "N39.0",
        ("Recurrent urinary tract infection",),
        ("Infections urinaires récidivantes",),
        "uro",
    ),
    "271737000": Condition("D64.9", ("Anaemia", "Anemia"), ("Anémie",), "haem"),
    "40055000": Condition("J32.9", ("Chronic sinusitis",), ("Sinusite chronique",), "ent"),
    "233678006": Condition("J45.909", ("Asthma",), ("Asthme",), "resp"),
    "185086009": Condition(
        "J44.9",
        ("Chronic obstructive pulmonary disease", "COPD"),
        ("Bronchopneumopathie chronique obstructive", "BPCO"),
        "resp",
    ),
    "78275009": Condition(
        "G47.33",
        ("Obstructive sleep apnoea", "Obstructive sleep apnea"),
        ("Syndrome d'apnées obstructives du sommeil",),
        "sleep",
    ),
    "39898005": Condition("G47.9", ("Sleep disorder",), ("Trouble du sommeil",), "sleep"),
    "124171000119105": Condition(
        "G43.719", ("Chronic migraine without aura",), ("Migraine chronique sans aura",), "neuro"
    ),
    "84757009": Condition("G40.909", ("Epilepsy",), ("Épilepsie",), "neuro"),
    "82423001": Condition("G89.29", ("Chronic pain",), ("Douleur chronique",), "pain"),
    "278860009": Condition(
        "M54.50", ("Chronic low back pain", "Low back pain"), ("Lombalgie chronique",), "pain"
    ),
    "1121000119107": Condition("M54.2", ("Chronic neck pain",), ("Cervicalgie chronique",), "pain"),
    "239873007": Condition(
        "M17.9",
        ("Osteoarthritis of the knee", "Knee osteoarthritis"),
        ("Gonarthrose", "Arthrose du genou"),
        "rheum",
    ),
    "239872002": Condition(
        "M16.9",
        ("Osteoarthritis of the hip", "Hip osteoarthritis"),
        ("Coxarthrose", "Arthrose de la hanche"),
        "rheum",
    ),
    "64859006": Condition("M81.0", ("Osteoporosis",), ("Ostéoporose",), "rheum"),
    "203082005": Condition("M79.7", ("Fibromyalgia",), ("Fibromyalgie",), "rheum"),
    "90560007": Condition("M10.9", ("Gout",), ("Goutte",), "rheum"),
    "66383009": Condition("K05.10", ("Gingivitis",), ("Gingivite",), "dental"),
}

FREQUENCIES: dict[str, dict[str, tuple[str, ...]]] = {
    "od": {"en": ("once daily", "OD", "every morning"), "fr": ("1 fois par jour", "le matin")},
    "bd": {"en": ("twice daily", "BD", "BID"), "fr": ("2 fois par jour", "matin et soir")},
    "tds": {"en": ("three times daily", "TDS", "TID"), "fr": ("3 fois par jour",)},
    "night": {"en": ("at night", "nocte"), "fr": ("le soir", "au coucher")},
    "prn": {"en": ("as needed", "PRN"), "fr": ("si besoin",)},
    "monthly": {"en": ("monthly", "once a month"), "fr": ("1 fois par mois",)},
    "weekly": {"en": ("once weekly",), "fr": ("1 fois par semaine",)},
    "q72h": {"en": ("every 72 hours",), "fr": ("toutes les 72 heures",)},
}

MEDICATIONS: dict[str, Medication] = {
    "lisinopril 10 MG Oral Tablet": Medication("Lisinopril", "Lisinopril", "10 mg", "od"),
    "Hydrochlorothiazide 25 MG Oral Tablet": Medication(
        "Hydrochlorothiazide", "Hydrochlorothiazide", "25 mg", "od"
    ),
    "amLODIPine 2.5 MG Oral Tablet": Medication("Amlodipine", "Amlodipine", "2.5 mg", "od"),
    "Nitroglycerin 0.4 MG/ACTUAT Mucosal Spray": Medication(
        "Glyceryl trinitrate spray", "Trinitrine spray", "0.4 mg", "prn"
    ),
    "24 HR metoprolol succinate 100 MG Extended Release Oral Tablet": Medication(
        "Metoprolol succinate MR", "Métoprolol LP", "100 mg", "od"
    ),
    "Simvastatin 20 MG Oral Tablet": Medication("Simvastatin", "Simvastatine", "20 mg", "night"),
    "Simvastatin 10 MG Oral Tablet": Medication("Simvastatin", "Simvastatine", "10 mg", "night"),
    "Clopidogrel 75 MG Oral Tablet": Medication("Clopidogrel", "Clopidogrel", "75 mg", "od"),
    "NDA020800 0.3 ML Epinephrine 1 MG/ML Auto-Injector": Medication(
        "Adrenaline auto-injector", "Adrénaline auto-injecteur", "0.3 mg", "prn"
    ),
    "Acetaminophen 300 MG / Hydrocodone Bitartrate 5 MG Oral Tablet": Medication(
        "Hydrocodone/paracetamol", "Hydrocodone/paracétamol", "5 mg/300 mg", "prn"
    ),
    "Naproxen sodium 220 MG Oral Tablet": Medication("Naproxen", "Naproxène", "220 mg", "bd"),
    "Ibuprofen 400 MG Oral Tablet [Ibu]": Medication("Ibuprofen", "Ibuprofène", "400 mg", "tds"),
    "Vitamin B12 5 MG/ML Injectable Solution": Medication(
        "Vitamin B12 injection", "Vitamine B12 injectable", "1 mg", "monthly"
    ),
    "Acetaminophen 325 MG Oral Tablet [Tylenol]": Medication(
        "Paracetamol", "Paracétamol", "325 mg", "prn"
    ),
    "ferrous sulfate 325 MG Oral Tablet": Medication(
        "Ferrous sulfate", "Sulfate ferreux", "325 mg", "od"
    ),
    "Loratadine 5 MG Chewable Tablet": Medication("Loratadine", "Loratadine", "5 mg", "od"),
    "24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet": Medication(
        "Metformin MR", "Metformine LP", "500 mg", "bd"
    ),
    "Fexofenadine hydrochloride 30 MG Oral Tablet": Medication(
        "Fexofenadine", "Fexofénadine", "30 mg", "od"
    ),
    "aspirin 81 MG Oral Tablet": Medication("Aspirin", "Aspirine", "81 mg", "od"),
    "Alendronic acid 10 MG Oral Tablet": Medication(
        "Alendronic acid", "Acide alendronique", "10 mg", "od"
    ),
    "albuterol 0.83 MG/ML Inhalation Solution": Medication(
        "Salbutamol nebules", "Salbutamol en nébulisation", "2.5 mg", "prn"
    ),
    "24 HR tacrolimus 1 MG Extended Release Oral Tablet": Medication(
        "Tacrolimus MR", "Tacrolimus LP", "1 mg", "od"
    ),
    "72 HR Fentanyl 0.025 MG/HR Transdermal System": Medication(
        "Fentanyl patch", "Fentanyl patch", "25 microgram/h", "q72h"
    ),
    "prasugrel 10 MG Oral Tablet": Medication("Prasugrel", "Prasugrel", "10 mg", "od"),
    "diphenhydrAMINE Hydrochloride 25 MG Oral Tablet": Medication(
        "Diphenhydramine", "Diphénhydramine", "25 mg", "night"
    ),
}

ALLERGIES: dict[str, tuple[str, str]] = {
    "Mold (organism)": ("Mould", "Moisissures"),
    "Animal dander (substance)": ("Animal dander", "Phanères d'animaux"),
    "House dust mite (organism)": ("House dust mite", "Acariens"),
    "Tree pollen (substance)": ("Tree pollen", "Pollen d'arbres"),
    "Grass pollen (substance)": ("Grass pollen", "Pollen de graminées"),
    "Shellfish (substance)": ("Shellfish", "Crustacés"),
    "Aspirin": ("Aspirin", "Aspirine"),
    "Bee venom (substance)": ("Bee venom", "Venin d'abeille"),
    "Eggs (edible) (substance)": ("Eggs", "Œufs"),
    "Latex (substance)": ("Latex", "Latex"),
    "Peanut (substance)": ("Peanut", "Arachide"),
    "Fish (substance)": ("Fish", "Poisson"),
    "Tree nut (substance)": ("Tree nuts", "Fruits à coque"),
    "Cow's milk (substance)": ("Cow's milk", "Lait de vache"),
    "Lisinopril": ("Lisinopril", "Lisinopril"),
    "Penicillin V": ("Penicillin", "Pénicilline"),
    "Sulfamethoxazole / Trimethoprim": ("Co-trimoxazole", "Cotrimoxazole"),
}
