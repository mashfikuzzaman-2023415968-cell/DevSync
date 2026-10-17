"""Image re-encoding with Pillow (§14.9): decode under a pixel budget (decompression-bomb guard),
apply the EXIF orientation, then write a brand-new file of the same type without any metadata
(EXIF, GPS, ICC, comments) and at most 4096 px on the longest side."""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps

from app.uploads.errors import UploadRejectedError

MAX_SIDE = 4096
MAX_PIXELS = 40_000_000  # ~6300 × 6300; larger images are refused before decoding fully
FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(frozen=True)
class CleanImage:
    data: bytes
    width: int
    height: int


def reencode(raw: bytes, mime: str) -> CleanImage:
    """Decode, normalise and re-encode; rejects anything Pillow won't trust."""
    fmt = FORMATS[mime]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as probe:
                if probe.format != fmt:
                    raise UploadRejectedError("The image type doesn't match its contents.")
                if probe.width * probe.height > MAX_PIXELS:
                    raise UploadRejectedError("The image has too many pixels.")
                probe.verify()
            with Image.open(io.BytesIO(raw)) as img:
                img.load()
                return _clean(img, fmt)
    except UploadRejectedError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise UploadRejectedError("The image has too many pixels.") from None
    except Exception:  # any decoder failure means "not a valid image"
        raise UploadRejectedError("The image file is damaged or not supported.") from None


def _clean(src: Image.Image, fmt: str) -> CleanImage:
    img = ImageOps.exif_transpose(src) or src
    if img.mode not in ("RGB", "RGBA", "L", "LA"):  # palette, CMYK, 1-bit, 16-bit…
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    # A fresh image: no exif=, icc_profile= or info carried over.
    params: dict[str, object] = {"optimize": True}
    if fmt in ("JPEG", "WEBP"):
        params["quality"] = 88
    clean = Image.new(img.mode, img.size)
    clean.paste(img)
    out = io.BytesIO()
    clean.save(out, format=fmt, **params)
    return CleanImage(out.getvalue(), clean.width, clean.height)
