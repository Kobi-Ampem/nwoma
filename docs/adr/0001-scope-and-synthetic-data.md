# ADR 0001: Scope and synthetic data

- Status: accepted
- Date: 2026-10-19

## Context

Nwoma extracts structured, coded data from clinical documents. Training and evaluating an extractor
needs documents with known correct answers. Real clinical documents are protected health data:
using them needs consent, legal agreements and secure hosting, and they would still need slow,
error-prone hand labelling.

## Decision

1. **Scope:** two document types, lab reports and referral letters, in English and French, as
   born-digital PDFs and as degraded scans.
2. **Synthetic data only.** Synthea (Apache 2.0) generates realistic patients with coded conditions,
   medications and lab results. Our generator renders them through layout templates and records the
   exact character span of every value it inserts.
3. **A held-out set of layouts** never seen in training, so the evaluation measures generalisation,
   not memorised templates.

## Consequences

- Labels are exact, so per-field precision, recall and F1 can be measured on thousands of documents.
- No privacy, consent or hosting obligations during development.
- **Main limitation:** a model trained on synthetic layouts may do worse on real documents. Unseen
  layouts, simulated scan damage and LLM-paraphrased letter text reduce the gap but do not remove it.
  The model card must state this, and any real-world claim needs a pilot on real documents first.
