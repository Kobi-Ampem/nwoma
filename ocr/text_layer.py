"""Get text out of a document: the PDF text layer when there is one, Tesseract OCR otherwise.

This is the runtime entry point the API uses, so it must not depend on the data generator.
"""

import io
import os
import subprocess
from typing import Literal

import pdfplumber
from PIL import Image

TextSource = Literal["text_layer", "ocr"]

# A born-digital page has far more than this; a scanned page has none.
_MIN_TEXT_LAYER_CHARS = 50
OCR_DPI = 200


def pdf_text(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


def ocr_image(image: Image.Image, langs: str = "eng+fra") -> str:
    """Run Tesseract on one page image. PSM 6 reads the page as one block of text, which keeps
    each table row on one line.

    Tesseract is limited to one thread: callers parallelise across pages or documents, and
    Tesseract's own OpenMP threads spin while waiting, so oversubscribed cores slow it ~15x."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", langs, "--psm", "6"],
        input=buffer.getvalue(),
        capture_output=True,
        check=True,
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    return result.stdout.decode("utf-8").rstrip("\n\f")


def pdf_pages_as_images(pdf: bytes, dpi: int = OCR_DPI) -> list[Image.Image]:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return [page.to_image(resolution=dpi).original.convert("L") for page in doc.pages]


def read_pdf(pdf: bytes) -> tuple[str, TextSource]:
    text = pdf_text(pdf)
    if len(text.strip()) >= _MIN_TEXT_LAYER_CHARS:
        return text, "text_layer"
    return "\n".join(ocr_image(page) for page in pdf_pages_as_images(pdf)), "ocr"
