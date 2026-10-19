"""Render a report to PDF, read its text back, and find exactly where each labelled value sits.

Spans are located in the text the extractor will actually see (the PDF text layer), not in the
HTML source, because layout changes spacing and line breaks.
"""

import io
from itertools import groupby
from pathlib import Path

import pdfplumber
import weasyprint
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from datagen.catalogue import PANELS
from datagen.compose import HEADER_LABELS
from datagen.models import EntityType, Field, LabReport, Span

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True, undefined=StrictUndefined
)

# How far after its label a header value may start, in characters.
_HEADER_WINDOW = 40


class SpanNotFoundError(ValueError):
    pass


def render_pdf(report: LabReport) -> bytes:
    groups = [
        (PANELS[panel][report.lang], list(rows))
        for panel, rows in groupby(enumerate(report.results), key=lambda r: r[1].panel)
    ]
    html = _env.get_template(f"{report.template}.html.j2").render(
        report=report, labels=HEADER_LABELS[report.lang], groups=groups
    )
    pdf: bytes = weasyprint.HTML(string=html).write_pdf()
    return pdf


def extract_text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def _span(label: EntityType, row: int | None, field: Field, start: int) -> Span:
    return Span(
        label=label,
        row=row,
        text=field.text,
        value=field.value,
        start=start,
        end=start + len(field.text),
    )


def locate_spans(text: str, report: LabReport) -> list[Span]:
    spans: list[Span] = []
    labels = HEADER_LABELS[report.lang]
    header: list[tuple[EntityType, Field]] = [
        ("PATIENT_NAME", report.patient_name),
        ("BIRTH_DATE", report.birth_date),
        ("SEX", report.sex),
        ("COLLECTION_DATE", report.collected_on),
        ("CLINICIAN", report.clinician),
    ]
    for label, field in header:
        anchor = text.find(labels[label])
        if anchor < 0:
            raise SpanNotFoundError(f"{report.doc_id}: header label {labels[label]!r} missing")
        after = anchor + len(labels[label])
        start = text.find(field.text, after, after + _HEADER_WINDOW + len(field.text))
        if start < 0:
            raise SpanNotFoundError(f"{report.doc_id}: {label} {field.text!r} not after its label")
        spans.append(_span(label, None, field, start))

    # Each result is one table row, so it must sit on one line that starts with the test name.
    lines: list[tuple[int, str]] = []
    offset = 0
    for line in text.split("\n"):
        lines.append((offset, line))
        offset += len(line) + 1

    line_idx = 0
    for row_idx, row in enumerate(report.results):
        while line_idx < len(lines) and not lines[line_idx][1].startswith(row.name.text + " "):
            line_idx += 1
        if line_idx == len(lines):
            raise SpanNotFoundError(f"{report.doc_id}: row {row.name.text!r} not found")
        line_start, line = lines[line_idx]
        line_end = line_start + len(line)
        cursor = line_start
        cells: list[tuple[EntityType, Field | None]] = [
            ("TEST_NAME", row.name),
            ("TEST_VALUE", row.value),
            ("TEST_UNIT", row.unit),
            ("REF_RANGE", row.ref_range),
            ("FLAG", row.flag),
        ]
        for label, cell in cells:
            if cell is None:
                continue
            start = text.find(cell.text, cursor, line_end)
            if start < 0:
                raise SpanNotFoundError(
                    f"{report.doc_id}: {label} {cell.text!r} not on row {row.name.text!r}"
                )
            spans.append(_span(label, row_idx, cell, start))
            cursor = start + len(cell.text)
        line_idx += 1
    return spans
