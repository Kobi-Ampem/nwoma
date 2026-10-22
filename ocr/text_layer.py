"""Get text out of a document: each page's text layer when it has one, Tesseract OCR otherwise.

This is the runtime entry point the API uses, so it must not depend on the data generator. A
public endpoint reads untrusted files, so the work is bounded: page count, page size, image
pixels, and a time limit on every OCR call. A small file can still decode into a huge job.
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
MAX_PAGES = 5  # lab reports and referral letters are one or two pages
MAX_PAGE_POINTS = 1500  # ~53 cm: larger than any real report page (A4 is 595 x 842)
MAX_IMAGE_PIXELS = 25_000_000  # ~A4 at 600 dpi
OCR_TIMEOUT_S = 30


class UnreadableDocument(ValueError):
    """The document cannot be read within the limits, or at all. The message is for the user."""


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
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", langs, "--psm", "6"],
            input=buffer.getvalue(),
            capture_output=True,
            check=True,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
            timeout=OCR_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired as e:
        raise UnreadableDocument("a page took too long to read") from e
    return result.stdout.decode("utf-8").rstrip("\n\f")


def pdf_pages_as_images(pdf: bytes, dpi: int = OCR_DPI) -> list[Image.Image]:
    with pdfplumber.open(io.BytesIO(pdf)) as doc:
        return [page.to_image(resolution=dpi).original.convert("L") for page in doc.pages]


def read_pdf(pdf: bytes) -> tuple[str, TextSource]:
    """Each page from its text layer, or by OCR when it has none: a digital cover page must
    not hide scanned pages behind it. Pages are handled one at a time to bound memory."""
    texts: list[str] = []
    used_ocr = False
    try:
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            if len(doc.pages) > MAX_PAGES:
                raise UnreadableDocument(f"documents are limited to {MAX_PAGES} pages")
            for page in doc.pages:
                if max(page.width, page.height) > MAX_PAGE_POINTS:
                    raise UnreadableDocument("a page is larger than any real report page")
                text = page.extract_text() or ""
                if len(text.strip()) < _MIN_TEXT_LAYER_CHARS:
                    image = page.to_image(resolution=OCR_DPI).original.convert("L")
                    text = ocr_image(image)
                    used_ocr = True
                texts.append(text)
    except UnreadableDocument:
        raise
    except Exception as e:  # pdfminer raises many types for damaged or encrypted files
        raise UnreadableDocument("the PDF is damaged or encrypted and cannot be read") from e
    return "\n".join(texts), "ocr" if used_ocr else "text_layer"


def read_image(data: bytes) -> str:
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise UnreadableDocument("the image is too large")
        return ocr_image(image.convert("L"))
    except UnreadableDocument:
        raise
    except Exception as e:  # not an image Pillow can decode
        raise UnreadableDocument("the file is not a PDF or an image") from e
