"""Render a report to PDF, read its text back, and find exactly where each labelled value sits.

Spans are located in the text the extractor will actually see (the PDF text layer), not in the
HTML source, because layout changes spacing and line breaks.
"""

from itertools import groupby
from pathlib import Path

import weasyprint
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from datagen.catalogue import PANELS
from datagen.layouts import LAYOUTS, Column, Layout
from datagen.models import EntityType, Field, LabReport, Lang, ResultRow, Span

TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True, undefined=StrictUndefined
)

_FOOTER: dict[Lang, str] = {
    "en": "Synthetic document generated for software testing. It does not describe a real patient.",
    "fr": "Document synthétique généré pour des tests logiciels. "
    "Il ne concerne aucun patient réel.",
}

_COLUMN_ENTITY: dict[Column, EntityType] = {
    "name": "TEST_NAME",
    "value": "TEST_VALUE",
    "unit": "TEST_UNIT",
    "ref": "REF_RANGE",
    "flag": "FLAG",
}

# How far after its label a header value may start, in characters.
_HEADER_WINDOW = 40


class SpanNotFoundError(ValueError):
    pass


def _cell(row: ResultRow, column: Column) -> Field | None:
    return {
        "name": row.name,
        "value": row.value,
        "unit": row.unit,
        "ref": row.ref_range,
        "flag": row.flag,
    }[column]


def _display(row: ResultRow, column: Column, layout: Layout) -> str:
    field = _cell(row, column)
    if field is None:
        return ""
    if column == "ref" and layout.ref_brackets:
        return f"({field.text})"
    return field.text


def render_pdf(report: LabReport) -> bytes:
    layout = LAYOUTS[report.template]
    groups = [
        (
            PANELS[panel][report.lang],
            [[(col, _display(row, col, layout)) for col in layout.columns] for row in rows],
        )
        for panel, rows in groupby(report.results, key=lambda r: r.panel)
    ]
    html = _env.get_template(f"{layout.skeleton}.html.j2").render(
        report=report, layout=layout, groups=groups, footer=_FOOTER[report.lang]
    )
    pdf: bytes = weasyprint.HTML(string=html).write_pdf()
    return pdf


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
    layout = LAYOUTS[report.template]
    spans: list[Span] = []
    header: list[tuple[EntityType, Field]] = [
        ("PATIENT_NAME", report.patient_name),
        ("BIRTH_DATE", report.birth_date),
        ("SEX", report.sex),
        ("COLLECTION_DATE", report.collected_on),
        ("CLINICIAN", report.clinician),
    ]
    for label, field in header:
        anchor_text = layout.anchor(label)
        anchor = text.find(anchor_text)
        if anchor < 0:
            raise SpanNotFoundError(f"{report.doc_id}: header label {anchor_text!r} missing")
        after = anchor + len(anchor_text)
        start = text.find(field.text, after, after + _HEADER_WINDOW + len(field.text))
        if start < 0:
            raise SpanNotFoundError(f"{report.doc_id}: {label} {field.text!r} not after its label")
        spans.append(_span(label, None, field, start))

    # Each result is one row, so it must sit on one line that starts with the test name.
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
        # Cells are searched in the layout's column order, so a flag "L" is never matched
        # inside a unit such as "mmol/L" that comes before it.
        for column in layout.columns:
            cell = _cell(row, column)
            if cell is None:
                continue
            label = _COLUMN_ENTITY[column]
            start = text.find(cell.text, cursor, line_end)
            if start < 0:
                raise SpanNotFoundError(
                    f"{report.doc_id}: {label} {cell.text!r} not on row {row.name.text!r}"
                )
            spans.append(_span(label, row_idx, cell, start))
            cursor = start + len(cell.text)
        line_idx += 1
    return spans
