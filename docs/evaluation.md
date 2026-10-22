# Evaluation report

Every number here is measured on held-out synthetic documents and reproducible from the
commands at the end. Results files are in `evals/results/`; the v1 results, before the layout
and referral-letter work, are in `evals/results/v1/`.

## Data and method

- **Documents:** 6,000 synthetic documents from 5,000 Synthea patients: 4,000 lab reports and
  2,000 referral letters, half French, half scanned (simulated scan damage, then Tesseract OCR).
  Labels are exact because each document is rendered from known values.
- **Splits by patient**, so no person appears in two: train 4,452, dev 447, test 514, and an
  unseen-layout test of 587 documents whose layouts no model trained on.
- **Evaluation sample:** a fixed 500 documents (seed 42): 150 lab reports and 100 referral
  letters from each of the test and unseen-layout splits. Every extractor is scored on the same
  500.
- **Scoring:** field-level precision, recall and F1 after one shared normaliser (dates to ISO,
  decimal commas, flag words to H/L). A wrong value counts as a false positive and a false
  negative. Fields OCR destroyed are left out of the truth. "Fully correct" means every field of
  the document is right.
- **Tuning on dev only:** prompts, the LOINC popularity weight and every threshold were chosen on
  the dev split. The test sample was used to measure, never to choose.

## 1. Extraction

| System | F1 | Fully correct | To the LLM | Seconds per document |
|---|---|---|---|---|
| Local model only (XLM-R, int8, CPU) | 0.920 | 57.8% | 0% | 0.15 |
| Gemini only (gemini-3.5-flash-lite) | 0.955 | 59.4% | 100% | 2.71 |
| **Cascade** (local first, Gemini when the validator objects) | **0.955** | **62.0%** | **32.8%** | **1.19** |
| Perfect routing (ceiling for any router) | 0.956 | 63.4% | 42.2% | 1.50 |

The cascade matches Gemini's F1 with a third of the calls and less than half the time, and gets
more documents fully right than either extractor alone: each wins on different documents (the
local model copies text exactly; Gemini repairs OCR damage). It is measured by running the
production `Cascade.run()`, which detects the document type itself (0 of 500 misdetected).

The validator caught 73% of the documents the local model got wrong (154 of 211), with 12 false
alarms in 500. On 1,101 perfect extractions it raised no issues. After the cascade, 26.4% of
documents still carry an issue for the reviewer.

### By slice

| Slice | Local model | Gemini |
|---|---|---|
| Lab reports | 0.909 | 0.950 |
| Referral letters | **0.981** | 0.980 |
| Digital | 0.969 | 0.999 |
| Scanned | 0.875 | 0.915 |
| Seen layouts | 0.946 | 0.947 |
| Unseen layouts | 0.893 | 0.963 |
| `ledger` lab layout (fresh, range before value) | 0.701 | 0.938 |

- **Scans** are where errors live. A model that copies text cannot recover what OCR destroyed:
  copying the true labels scores 0.888 on scans, and the local model reaches 0.875. Gemini goes
  past that ceiling (0.915) because it corrects some OCR errors.
- **Referral letters:** the local model matches Gemini, and beats it on the reason for referral
  (0.995 vs 0.927), where Gemini sometimes rewrites instead of copying.

### The layout finding (ADR 0002)

The local model learns the order fields come in, not what they mean. v1 missed flags on unseen
layouts that moved the flag. v2 added training layouts covering those orders; it improved on the
layouts already examined (`list`: 0.924 to 0.964) and got worse on a fresh held-out layout
(`ledger`: 0.727 to 0.681), whose range comes before the value. Only the fresh layout showed the
fix had not generalised. Its errors are confident, so routing uses validator checks, not model
confidence.

| Layout family | NER v1 | NER v2 | Gemini |
|---|---|---|---|
| Seen in training | 0.90–0.96 | 0.92–0.96 | 0.92–0.96 |
| `list` (examined after v1) | 0.924 | 0.964 | 0.971 |
| `ledger` (fresh) | 0.727 | 0.681 | 0.939 |

### Field-level weak spots

| Field | Local model | Gemini |
|---|---|---|
| Flag (H/L) | 0.710 | 0.896 |
| Unit | 0.881 | 0.910 |
| Value | 0.900 | 0.966 |
| Reference range | 0.901 | 0.949 |
| Reason for referral | 0.995 | 0.927 |

## 2. Code mapping

Top-1: the first suggestion is right. Top-5: the right code is among the five the reviewer sees.

### Lab tests to LOINC (9,092 result rows; 3,455 candidate codes)

| Method | Top-1 | Top-5 | Same test, any method |
|---|---|---|---|
| Keyword search (BM25 on character trigrams) | 3.6% | 34.6% | 16.2% |
| Semantic search (multilingual E5 embeddings) | 3.6% | 39.3% | 13.9% |
| Hybrid (reciprocal rank fusion) | 3.6% | 35.7% | 15.6% |
| + unit and specimen | 19.6% | 65.5% | 54.4% |
| **+ popularity prior** (tuned on dev) | **59.8%** | **81.0%** | **73.6%** |

Search alone finds the right area but cannot choose: LOINC has dozens of near-identical codes per
test, differing by specimen, method or property. The unit (mass vs moles), the specimen and how
commonly each code is used do the choosing. Dev and test agree (60.7% vs 59.8% top-1).

### Diagnoses to ICD-10-CM (74,879 billable codes)

| Method | Top-1 EN | Top-5 EN | Top-1 FR | Top-5 FR |
|---|---|---|---|---|
| Keyword | 18.2% | 67.3% | 16.3% | 48.8% |
| Semantic | 29.1% | 47.3% | 25.6% | 41.9% |
| Hybrid | 25.5% | 56.4% | 30.2% | 55.8% |
| **+ ICD-10-CM coding rules** | **43.6%** | **76.4%** | **44.2%** | **65.1%** |

The coding rules are fixed, published conventions, not tuned weights: undocumented detail is
coded as unspecified, diabetes of unstated type is type 2, and pregnancy or newborn codes need
those words. French reaches English descriptions through the multilingual embeddings alone; no
French code table is used.

## 3. Coding agent

Gemini with four tools (`search_loinc`, `search_icd10`, `check_range`, `read_document`) and at
most five steps, ending with a forced `submit_codes`. It sees the same printed names as the mapper
and can rephrase a search, expand an abbreviation, or read the document for context. Scored item
by item against the mapper's first suggestion on 40 documents (seed 7): 229 lab results and 57
diagnoses.

| | Mapper top-1 | Agent | Mapper, close | Agent, close |
|---|---|---|---|---|
| Lab test → LOINC | 64.2% | **85.2%** | 76.0% | **96.9%** |
| Diagnosis → ICD-10-CM | 49.1% | **93.0%** | 63.2% | **96.5%** |

"Close" is the same test (component, property, specimen) for LOINC and the same three-character
category for ICD-10-CM. The agent fixes exactly what search cannot: French abbreviations (`VGM`,
`TCMH`, `CCMH`, `VPM` to the right MCV, MCH, MCHC, MPV codes), French names (`Globules rouges`,
`Leucocytes`) and specimen choices (`Ca` to total, not ionised, calcium).

Cost: 3.5 model calls and about 7,500 tokens per document, against none for the mapper. It is an
upgrade for the paid tier, not the default. Two failures during the evaluation became fixes:
calls are paced under the free tier's 15 requests a minute, and a tool called with unexpected
arguments returns an error to the model instead of ending the run. The prompt's examples (`TSH`,
`Ferritinémie`) appear nowhere in the evaluation data.

## 4. Speed and cost

| | Local model | Gemini | Cascade |
|---|---|---|---|
| Median latency per document | 0.13 s | 2.0 s | ~1.2 s mean |
| Tokens per document | none | ~470 in, ~580 out | a third of Gemini's |
| Cost | none | free tier, 500 requests/day | 3x more documents per day than Gemini alone |

Deployment: one AWS Lambda container (3 GB) behind a function URL, about $0.25 a month (ADR 0003).
A cold start takes minutes (the 2 GB image loads lazily); a keep-warm ping every 5 minutes keeps
one instance loaded.

## 5. Limitations

- **Synthetic data.** Real documents vary more; expect lower scores until evaluated on real,
  consented, de-identified documents.
- **Unseen column orders** break the local model (above); the cascade covers them with Gemini.
- **OCR** can drop the first line inside a bordered box (issue #16); missing required fields are
  flagged.
- **Code suggestions** are right first time about half the time, so a person chooses from five.
- **One LLM, one sample.** Gemini figures come from one model. On the earlier 200-document
  sample, the bootstrap 95% interval on Gemini's overall F1 was ±0.009; on 500 documents it is
  narrower, but differences under about 0.01 should not be read as real.

## Reproduce

```
uv run python -m datagen.build --n 4000 --n-referral 2000 --workers 6   # data (about 30 min)
uv run python -m evals.run_llm --per-split 150 --per-split-referral 100  # Gemini (cached)
uv run python -m evals.run_ner --per-split 150 --per-split-referral 100  # local model
uv run python -m evals.run_cascade                                       # cascade
uv run python -m evals.run_codes                                         # LOINC
uv run python -m evals.run_icd10                                         # ICD-10-CM
uv run python -m evals.run_agent --docs 20                               # coding agent
```
