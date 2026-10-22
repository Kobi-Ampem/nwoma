# Model card: Nwoma field tagger (XLM-RoBERTa-base, int8 ONNX)

## Summary

A token classifier that tags the fields of clinical lab reports and referral letters, in English
and French, in text read from a PDF or by OCR. It is the first stage of Nwoma's extraction
cascade: it runs locally in about 0.13 s per document, and documents the validator objects to go
to an LLM.

| | |
|---|---|
| Base model | `FacebookAI/xlm-roberta-base` (278M parameters, multilingual) |
| Task | Token classification, BIO tags over 16 field types (33 labels) |
| Format | ONNX, dynamic int8 quantisation, 278 MB |
| Runtime | onnxruntime on CPU, one thread; no PyTorch needed |
| Code | `extract/train_ner.py` (training), `extract/ner.py` (inference), `notebooks/train_ner.ipynb` |
| Version | v3, 21 October 2026 |

## Intended use

- **For:** turning the text of a lab report or referral letter into structured fields, for a
  person to review before the record is saved.
- **Not for:** diagnosis, interpretation of results, treatment decisions, or any use without
  human review. It transcribes what is printed; it does not judge it.
- **Not for real patient data** in this form: it was trained and evaluated on synthetic documents
  only (below).

## Fields

| Lab reports | Referral letters | Both |
|---|---|---|
| COLLECTION_DATE, TEST_NAME, TEST_VALUE, TEST_UNIT, REF_RANGE, FLAG | REASON, DIAGNOSIS, MEDICATION, DOSE, FREQUENCY, ALLERGY | PATIENT_NAME, BIRTH_DATE, SEX, CLINICIAN |

## Training data

Synthetic only, so every label is exact and no real patient data is used (ADR 0001).

- **Source:** 5,000 Synthea patients (seed 42), rendered through templates into 4,000 lab reports
  and 2,000 referral letters, half French, half scanned (skew, blur, noise, JPEG damage, then
  Tesseract OCR with labels projected onto the OCR text).
- **Layouts:** 18 lab-report layouts on 5 skeletons and 6 referral layouts on 3 skeletons. Some
  skeletons are held out of training entirely, to test unseen layouts.
- **Splits, by patient** (no person appears in two): train 4,452 documents (4,749 windows of up
  to 512 tokens), dev 447, test 514, unseen-layout test 587.
- Each patient contributes at most 2 visits, so chronically ill patients do not dominate.

## Training

Colab T4 GPU, about 6 minutes: 3 epochs, learning rate 3e-5, batch 16, 10% warm-up, weight decay
0.01. Dev loss fell every epoch (0.0163, 0.0135, 0.0133). The ONNX export was checked against
PyTorch on 35 padded windows (largest logit difference 2.4e-5) before quantising.

## Evaluation

500 held-out documents (300 lab reports, 200 referral letters; test and unseen-layout splits),
the same documents as the Gemini baseline. F1 over every field, after the shared normaliser.

| Slice | F1 | Documents fully correct |
|---|---|---|
| All | 0.920 | 57.8% |
| Lab reports | 0.909 | 44.7% |
| Referral letters | 0.981 | 77.5% |
| Digital / scanned | 0.969 / 0.875 | |
| English / French | 0.947 / 0.891 | |
| Seen layouts / unseen layouts | 0.947 / 0.893 | |

By field: dates, sex, clinician 0.97 to 0.99; test names 0.96; values 0.90; units 0.88; ranges
0.90; **flags 0.71**; referral fields 0.97 to 1.00.

Ceiling on scans: a model that copies text cannot recover what OCR destroyed; copying perfect
labels scores 0.888 on scans. The model reaches 0.875 there.

Comparison: Gemini reaches 0.955 on the same documents (2.7 s per document); the cascade, local
model first and Gemini when the validator objects, also reaches 0.955 with 33% of documents sent
to Gemini, and 62.0% of documents fully correct. See `docs/evaluation.md`.

## Limitations

- **Column order (ADR 0002).** The model learns the order fields appear in. On the unseen
  `ledger` lab layout, which puts the range before the value, F1 falls to 0.70. Its errors there
  are confident, so the cascade routes on validator checks, not confidence.
- **Flags** are the weakest field (0.71): short tokens in positions that vary by layout.
- **OCR damage** caps scanned documents; the first line inside a bordered box can be lost
  (issue #16).
- **French** scores lower than English (0.891 vs 0.947), mostly through scans and unseen layouts.
- **Synthetic data:** real documents vary more in layout, wording and damage. Expect lower
  scores until evaluated on real, consented, de-identified documents.

## Ethical considerations

- A transcription error in a clinical record can harm a patient. The model is only ever a first
  pass: uncertain fields are flagged, and the exported FHIR record says which fields a named
  person verified (Provenance).
- No real patient data was used to train or evaluate it.
- The public demo stores nothing.
