"""File type by content signature (libmagic), never by name or the browser's Content-Type, plus
structural checks that catch polyglots — files that are valid in two formats at once, such as an
image with a ZIP or HTML document appended, or a PDF carrying scripts or embedded files.
"""

from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

import magic

from app.uploads.errors import UploadRejectedError

IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
PDF_TYPE = "application/pdf"
TEXT_TYPE = "text/plain"
SNIFF_BYTES = 8192

# Markers of other formats or active content that must never ride along inside an upload.
_FOREIGN_SIGNATURES = (
    b"PK\x03\x04",  # ZIP (also docx/jar/apk)
    b"PK\x05\x06",
    b"Rar!\x1a\x07",
    b"7z\xbc\xaf\x27\x1c",
    b"MZ\x90\x00",  # Windows executable
    b"\x7fELF",
)
_ACTIVE_MARKUP = re.compile(rb"<\s*(?:html|script|svg|iframe|object|embed)\b", re.IGNORECASE)
_PDF_ACTIVE = re.compile(
    rb"/(?:JavaScript|JS|Launch|EmbeddedFile|EmbeddedFiles|OpenAction|AA|RichMedia|XFA|SubmitForm"
    rb"|ImportData|GoToR|GoToE)(?![A-Za-z0-9])"
)
_PDF_NAME_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")
_PDF_STREAM = re.compile(rb"stream\r?\n(.*?)endstream", re.DOTALL)
# Decompressing every stream is bounded so a compression bomb can't exhaust memory.
PDF_INFLATE_BUDGET = 64 * 1024 * 1024


def sniff(path: Path) -> str:
    """MIME type from the file's leading bytes."""
    with path.open("rb") as fh:
        head = fh.read(SNIFF_BYTES)
    if not head:
        raise UploadRejectedError("The file is empty.")
    return str(magic.from_buffer(head, mime=True))


def _png_end(data: bytes) -> int:
    """Offset just after the IEND chunk (raises if the chunk structure is broken)."""
    pos = 8
    while pos + 12 <= len(data):
        length = int(struct.unpack(">I", data[pos : pos + 4])[0])
        kind = data[pos + 4 : pos + 8]
        pos += 12 + length
        if kind == b"IEND":
            return pos
    raise UploadRejectedError("The image file is damaged.")


def _webp_end(data: bytes) -> int:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise UploadRejectedError("The image file is damaged.")
    return 8 + int(struct.unpack("<I", data[4:8])[0])


TRAILING_SLACK = 16  # bytes of padding tolerated after an image's end marker


def _jpeg_end(data: bytes) -> int:
    end = data.rfind(b"\xff\xd9")
    if end < 0:
        raise UploadRejectedError("The image file is damaged.")
    return end + 2


def check_structure(path: Path, mime: str) -> None:
    """Reject polyglots: trailing data after an image ends, foreign signatures, active content."""
    data = path.read_bytes()
    if mime in IMAGE_TYPES:
        end = {"image/png": _png_end, "image/webp": _webp_end, "image/jpeg": _jpeg_end}[mime](data)
        # A few bytes of padding are normal; anything substantial after the image is not.
        if len(data) - end > TRAILING_SLACK:
            raise UploadRejectedError("The image contains extra data after its end.")
        body = data[:end]
    else:
        body = data
    scan = body[16:] if mime in IMAGE_TYPES else body  # skip the file's own magic number
    if any(sig in scan for sig in _FOREIGN_SIGNATURES):
        raise UploadRejectedError("The file contains another file inside it.")
    if _ACTIVE_MARKUP.search(body):
        raise UploadRejectedError("The file contains web page or script content.")
    if mime == PDF_TYPE:
        _check_pdf(data)
    if mime == TEXT_TYPE:
        _check_text(data)


def _unescape_names(data: bytes) -> bytes:
    """PDF names may spell letters as #xx (`/J#61vaScript`); decode before matching."""
    return _PDF_NAME_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), data)


def _inflated_streams(data: bytes) -> list[bytes]:
    """Contents of Flate-compressed streams (object streams can hide actions), bounded."""
    out: list[bytes] = []
    budget = PDF_INFLATE_BUDGET
    for match in _PDF_STREAM.finditer(data):
        inflater = zlib.decompressobj()
        try:
            chunk = inflater.decompress(match.group(1), budget + 1)
        except zlib.error:
            continue  # not Flate (e.g. an image codec): nothing to scan as PDF syntax
        budget -= len(chunk)
        if budget < 0 or inflater.unconsumed_tail:
            raise UploadRejectedError("The PDF file is too complex to check.")
        out.append(chunk)
    return out


def _check_pdf(data: bytes) -> None:
    if not data.startswith(b"%PDF-") or not data.rstrip().endswith(b"%%EOF"):
        raise UploadRejectedError("The PDF file is damaged.")
    for part in (data, *_inflated_streams(data)):
        plain = _unescape_names(part)
        if _PDF_ACTIVE.search(plain) or _ACTIVE_MARKUP.search(plain):
            raise UploadRejectedError("PDFs with scripts, actions or attachments aren't accepted.")
        if any(sig in plain for sig in _FOREIGN_SIGNATURES):
            raise UploadRejectedError("The file contains another file inside it.")


def _check_text(data: bytes) -> None:
    if b"\x00" in data:
        raise UploadRejectedError("The text file contains binary data.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise UploadRejectedError("Text files must be UTF-8.") from None
