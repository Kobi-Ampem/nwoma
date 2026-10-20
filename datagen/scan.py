"""Make a clean rendered page look like a scan or a phone photo of paper."""

import io
import random

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


def degrade(page: Image.Image, rng: random.Random) -> Image.Image:
    """Apply a random mix of the damage real scans show. Expects a greyscale page."""
    img = page.convert("L")

    # Skew: pages are rarely fed perfectly straight.
    img = img.rotate(rng.uniform(-1.5, 1.5), resample=Image.Resampling.BICUBIC, fillcolor=255)

    # Lower effective resolution, then back up: fine strokes go soft.
    scale = rng.uniform(0.45, 0.9)
    small = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.BILINEAR)
    img = small.resize(img.size, Image.Resampling.BILINEAR)

    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.0, 1.3)))
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.7, 1.1))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.9, 1.1))

    # Sensor and paper noise.
    pixels = np.asarray(img, dtype=np.float32)
    noise = np.random.default_rng(rng.randrange(2**32)).normal(0, rng.uniform(3, 20), pixels.shape)
    img = Image.fromarray(np.clip(pixels + noise, 0, 255).astype(np.uint8))

    # Lossy compression, as from a phone or a scanner set to JPEG.
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=rng.randint(35, 75))
    buffer.seek(0)
    return Image.open(buffer).convert("L")


def images_to_pdf(pages: list[Image.Image], dpi: int) -> bytes:
    """An image-only PDF, like a scanner produces: no text layer."""
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:], resolution=dpi)
    return buffer.getvalue()
