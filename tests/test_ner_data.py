"""Span <-> token tag conversion, with a whitespace tokenizer standing in for XLM-R."""

import re
from typing import Any

from datagen.models import EntityType, Span
from extract.ner_data import IGNORE, LABEL2ID, LABELS, decode, encode, to_extraction


def _fake_tokenizer(text: str, **_: Any) -> dict[str, list[list[Any]]]:
    """One window: <s>, one token per non-space run, </s>."""
    offsets = [(0, 0)] + [m.span() for m in re.finditer(r"\S+", text)] + [(0, 0)]
    return {
        "input_ids": [list(range(len(offsets)))],
        "attention_mask": [[1] * len(offsets)],
        "offset_mapping": [offsets],
    }


def _span(text: str, part: str, label: EntityType) -> Span:
    start = text.index(part)
    return Span(label=label, row=0, text=part, value=part, start=start, end=start + len(part))


TEXT = "Name: Anne Chauvin\nGlucose 5,4 mmol/L (3,9 - 5,8) H"


def test_encode_tags_b_then_i_and_ignores_special_tokens() -> None:
    spans = [_span(TEXT, "Anne Chauvin", "PATIENT_NAME"), _span(TEXT, "3,9 - 5,8", "REF_RANGE")]
    tags = [
        LABELS[t] if t != IGNORE else "-" for t in encode(_fake_tokenizer, TEXT, spans)[0]["labels"]
    ]
    # <s> Name: Anne Chauvin Glucose 5,4 mmol/L (3,9 - 5,8) H </s>
    assert tags == [
        "-", "O", "B-PATIENT_NAME", "I-PATIENT_NAME", "O", "O", "O",
        "B-REF_RANGE", "I-REF_RANGE", "I-REF_RANGE", "O", "-",
    ]  # fmt: skip


def test_a_token_starting_outside_a_span_still_carries_it() -> None:
    # '(3,9' starts with '(' which is not part of the range.
    tags = encode(_fake_tokenizer, TEXT, [_span(TEXT, "3,9 - 5,8", "REF_RANGE")])[0]["labels"]
    assert LABEL2ID["B-REF_RANGE"] in tags


def test_decode_inverts_encode() -> None:
    spans = [_span(TEXT, "Glucose", "TEST_NAME"), _span(TEXT, "mmol/L", "TEST_UNIT")]
    enc = _fake_tokenizer(TEXT)
    labels = encode(_fake_tokenizer, TEXT, spans)[0]["labels"]
    got = decode(enc["offset_mapping"][0], [max(t, 0) for t in labels])
    assert got == [(s.label, s.start, s.end) for s in spans]


def test_a_stray_i_tag_starts_a_new_span() -> None:
    i_unit = LABEL2ID["I-TEST_UNIT"]
    assert decode([(0, 4), (5, 9)], [LABEL2ID["O"], i_unit]) == [("TEST_UNIT", 5, 9)]


def test_rows_are_assembled_from_spans_in_order() -> None:
    text = "Na 140 mmol/L K 6,1 mmol/L H"
    spans = [
        ("TEST_NAME", 0, 2), ("TEST_VALUE", 3, 6), ("TEST_UNIT", 7, 13),
        ("TEST_NAME", 14, 15), ("TEST_VALUE", 16, 19), ("TEST_UNIT", 20, 26), ("FLAG", 27, 28),
    ]  # fmt: skip
    ext = to_extraction(text, spans)
    assert [(r.test_name, r.value, r.flag) for r in ext.results] == [
        ("Na", "140", None),
        ("K", "6,1", "H"),
    ]


def test_a_repeated_row_field_starts_a_new_row_without_a_name() -> None:
    # The second test name was lost to OCR: its value must not overwrite the first row's.
    ext = to_extraction(
        "Na 140 138", [("TEST_NAME", 0, 2), ("TEST_VALUE", 3, 6), ("TEST_VALUE", 7, 10)]
    )
    assert [(r.test_name, r.value) for r in ext.results] == [("Na", "140"), ("", "138")]
