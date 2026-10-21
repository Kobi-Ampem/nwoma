# ADR 0002: The NER model's layout limit, and routing around it

- Status: accepted
- Date: 2026-10-21

## Context

The fine-tuned NER model (XLM-RoBERTa-base, int8 ONNX, 116 ms per document on one CPU thread)
matches Gemini on layouts it was trained on: digital F1 1.000 on seen layouts. On unseen layouts it
breaks when fields appear in an order it never saw (issue #17):

| Skeleton (300-doc v2 sample) | NER v1 | NER v2 | Gemini |
|---|---|---|---|
| seen (boxed, sidebar, table) | 0.90–0.96 | 0.92–0.96 | 0.92–0.96 |
| list (examined after v1) | 0.924 | 0.964 | 0.971 |
| ledger (fresh, range before value) | 0.727 | 0.681 | 0.939 |

v2 added training layouts covering the flag positions v1 missed. It fixed those and got worse on
an order nobody had trained for: on `Kaliémie 3,5 - 5,1 4,0 mmol/L` it tags `4` as a flag and `0`
as the value. A token classifier learns the sequence fields come in, not what a field means.

The model's errors here are confident. It does not tag the flag with low confidence; it tags it
`O`. Routing on the model's own confidence cannot catch them.

## Decision

1. **Stop iterating on layout coverage.** Each added layout fixes its own column order and can
   break another. Results stay on record as v1 and v2.
2. **NER is the first stage for documents in familiar layouts.** A hospital receives reports from
   a limited set of labs, so most traffic is in layouts that can be trained once.
3. **The cascade (issue #8) routes on structural checks, not only confidence.** A document goes
   to the LLM when its extraction is implausible, for example:
   - a result row with a range but no value, or a value that is not a number;
   - a flag that disagrees with the value and range printed beside it;
   - required header fields missing;
   - a number split across fields (`4` / `,` / `0`).
4. **Measure the cascade on `ledger`** as part of the final evaluation, reported as an examined
   layout. Any further layout-generalisation work needs a new, unexamined held-out skeleton.

## Alternatives considered

- **Shuffle column order per training document.** Teaches order independence in general. Likely to
  help, but needs a third fresh layout to measure honestly and about 1.5 hours plus a Colab run.
  Revisit if the cascade sends too many documents to the LLM.
- **Gemini only.** Best accuracy, simplest. Loses local, private and free extraction, which is
  the Free tier's whole engine, and the per-document cost and quota limits come back.

## Consequences

- The cascade needs a validator before it needs a confidence threshold.
- The evaluation report must show results by skeleton, with seen, examined and fresh layouts
  labelled, so nobody reads the `list` improvement as generalisation.
