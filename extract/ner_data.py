"""Convert between labelled character spans and the token tags the NER model learns.

The labels are character spans; the model sees subword tokens. Each token takes the tag of the
first span it overlaps: B- for the span's first token, I- for the rest, O outside any span.
Special tokens get -100, which the training loss ignores.

Documents longer than the model's 512-token limit (multi-page reports, and scans where OCR read
page noise as text) are cut into overlapping windows, so a field cut at one window's edge is
whole in the next.

This module has no PyTorch dependency: the API uses `decode` and `to_extraction` at runtime.
"""

from typing import Any, get_args

from datagen.models import EntityType, Span
from extract.schema import ExtractedMedication, ExtractedResult, Extraction

ENTITY_TYPES: list[str] = list(get_args(EntityType))
LABELS = ["O"] + [f"{p}-{t}" for t in ENTITY_TYPES for p in ("B", "I")]
LABEL2ID = {label: i for i, label in enumerate(LABELS)}
MAX_LEN = 512
STRIDE = 128  # tokens shared by consecutive windows
IGNORE = -100

_HEADER = {
    "PATIENT_NAME": "patient_name",
    "BIRTH_DATE": "birth_date",
    "SEX": "sex",
    "COLLECTION_DATE": "collection_date",
    "CLINICIAN": "clinician",
    "REASON": "reason",
}
_MEDICATION = {"MEDICATION": "name", "DOSE": "dose", "FREQUENCY": "frequency"}
_ROW = {
    "TEST_NAME": "test_name",
    "TEST_VALUE": "value",
    "TEST_UNIT": "unit",
    "REF_RANGE": "ref_range",
    "FLAG": "flag",
}


def windows(tokenizer: Any, text: str) -> Any:
    """Tokenise into overlapping windows, keeping each token's character offsets."""
    return tokenizer(
        text,
        truncation=True,
        max_length=MAX_LEN,
        stride=STRIDE,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
    )


def encode(tokenizer: Any, text: str, spans: list[Span]) -> list[dict[str, list[int]]]:
    """Training examples, one per window: input ids, attention mask and a tag per token."""
    owner = [-1] * len(text)  # index of the span covering each character
    for k, span in enumerate(spans):
        owner[span.start : span.end] = [k] * (span.end - span.start)
    enc = windows(tokenizer, text)
    examples = []
    for w, offsets in enumerate(enc["offset_mapping"]):
        tags: list[int] = []
        started: set[int] = set()
        for start, end in offsets:
            # The first span the token overlaps, not the span at its first character: in
            # '(12.0 - 17.5)' the token '(12' starts outside the range but carries its number.
            k = next((owner[c] for c in range(start, end) if owner[c] >= 0), -1)
            if start == end:
                tags.append(IGNORE)  # <s>, </s>: not part of the text
            elif k < 0:
                tags.append(LABEL2ID["O"])
            else:
                prefix = "I" if k in started else "B"
                started.add(k)
                tags.append(LABEL2ID[f"{prefix}-{spans[k].label}"])
        examples.append(
            {
                "input_ids": enc["input_ids"][w],
                "attention_mask": enc["attention_mask"][w],
                "labels": tags,
            }
        )
    return examples


def decode(offsets: list[tuple[int, int]], label_ids: list[int]) -> list[tuple[str, int, int]]:
    """Token tags back to (label, start, end) character spans, in document order.

    `offsets` must be sorted and without duplicates (windows merged). An I- tag that does not
    continue an open span of its type starts a new one: a model's slightly wrong B/I choice
    should not cost the whole field.
    """
    spans: list[tuple[str, int, int]] = []
    open_label: str | None = None
    for (start, end), label_id in zip(offsets, label_ids, strict=True):
        if start == end:
            continue
        tag = LABELS[label_id]
        if tag == "O":
            open_label = None
            continue
        prefix, label = tag.split("-", 1)
        if prefix == "I" and open_label == label:
            spans[-1] = (label, spans[-1][1], end)
        else:
            spans.append((label, start, end))
            open_label = label
    return spans


def to_extraction(text: str, spans: list[tuple[str, int, int]]) -> Extraction:
    """Assemble spans into the shared output shape.

    Header fields keep their first occurrence. A test name starts a new result row and a
    medication name a new medication row; any other row field joins the current row, or starts a
    new one if the current row already has it. Diagnoses and allergies are plain lists.
    """
    header: dict[str, str] = {}
    rows: list[dict[str, str]] = []
    meds: list[dict[str, str]] = []
    lists: dict[str, list[str]] = {"DIAGNOSIS": [], "ALLERGY": []}
    for label, start, end in spans:
        value = " ".join(text[start:end].split())  # a wrapped field reads as one line
        if label in _HEADER:
            header.setdefault(_HEADER[label], value)
        elif label in lists:
            lists[label].append(value)
        elif label in _MEDICATION:
            field = _MEDICATION[label]
            if label == "MEDICATION" or not meds or field in meds[-1]:
                meds.append({})
            meds[-1][field] = value
        else:
            field = _ROW[label]
            if label == "TEST_NAME" or not rows or field in rows[-1]:
                rows.append({})
            rows[-1][field] = value
    return Extraction(
        patient_name=header.get("patient_name"),
        birth_date=header.get("birth_date"),
        sex=header.get("sex"),
        collection_date=header.get("collection_date"),
        clinician=header.get("clinician"),
        reason=header.get("reason"),
        results=[
            ExtractedResult(
                test_name=r.get("test_name", ""),
                value=r.get("value", ""),
                unit=r.get("unit"),
                ref_range=r.get("ref_range"),
                flag=r.get("flag"),
            )
            for r in rows
        ],
        diagnoses=lists["DIAGNOSIS"],
        medications=[
            ExtractedMedication(
                name=m.get("name", ""), dose=m.get("dose"), frequency=m.get("frequency")
            )
            for m in meds
        ],
        allergies=lists["ALLERGY"],
    )
