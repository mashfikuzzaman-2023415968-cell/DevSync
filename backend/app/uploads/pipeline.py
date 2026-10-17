"""The upload pipeline (§14.9): stream to a private temp file under a size limit, identify the
type by signature, reject polyglots and active content, re-encode images, then store the clean
bytes under a random key. Each file kind accepts only the types it needs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.models.profiles import FileKind
from app.uploads import detect
from app.uploads.errors import UploadRejectedError, UploadTooLargeError
from app.uploads.images import reencode
from app.uploads.storage import Readable, Storage, sanitize_name

MB = 1024 * 1024
PDF_MAX_BYTES = 10 * MB
TEXT_MAX_BYTES = 1 * MB

ALLOWED: dict[FileKind, frozenset[str]] = {
    FileKind.PORTFOLIO_IMAGE: detect.IMAGE_TYPES,
    FileKind.CERTIFICATE: detect.IMAGE_TYPES | {detect.PDF_TYPE},
    FileKind.EXTERNAL_REVIEW: detect.IMAGE_TYPES | {detect.PDF_TYPE, detect.TEXT_TYPE},
}
_DESCRIBE = {
    FileKind.PORTFOLIO_IMAGE: "PNG, JPEG or WebP images",
    FileKind.CERTIFICATE: "PDF files or PNG, JPEG or WebP images",
    FileKind.EXTERNAL_REVIEW: "PDF, plain text, or PNG, JPEG or WebP images",
}
_EXTENSION = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    detect.PDF_TYPE: ".pdf",
    detect.TEXT_TYPE: ".txt",
}


@dataclass(frozen=True)
class StoredUpload:
    """A clean file that is now on disk under `storage_key`."""

    storage_key: str
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    width: int | None
    height: int | None


def type_limit(mime: str, max_upload_bytes: int) -> int:
    """Size limit for one type (PDF 10 MB and text 1 MB, never above MAX_UPLOAD_MB)."""
    if mime == detect.PDF_TYPE:
        return min(PDF_MAX_BYTES, max_upload_bytes)
    if mime == detect.TEXT_TYPE:
        return min(TEXT_MAX_BYTES, max_upload_bytes)
    return max_upload_bytes


def _display_name(name: str | None, mime: str) -> str:
    """Sanitized name whose extension matches the detected type (never the claimed one)."""
    stem = sanitize_name(name).rsplit(".", 1)[0] or "file"
    return stem[:100] + _EXTENSION[mime]


def _clean_bytes(path: Path, mime: str) -> tuple[bytes, int | None, int | None]:
    detect.check_structure(path, mime)
    raw = path.read_bytes()
    if mime in detect.IMAGE_TYPES:
        img = reencode(raw, mime)
        return img.data, img.width, img.height
    return raw, None, None


async def accept_upload(
    storage: Storage,
    source: Readable,
    *,
    kind: FileKind,
    filename: str | None,
    max_upload_bytes: int,
) -> StoredUpload:
    """Run the whole pipeline; raises UploadRejectedError / UploadTooLargeError."""
    allowed = ALLOWED[kind]
    async with storage.receive(source, max_upload_bytes) as path:
        mime = detect.sniff(path)
        if mime not in allowed:
            raise UploadRejectedError(f"Only {_DESCRIBE[kind]} are accepted here.")
        limit = type_limit(mime, max_upload_bytes)
        if path.stat().st_size > limit:
            raise UploadTooLargeError(f"This type of file can be at most {limit // MB} MB.")
        data, width, height = _clean_bytes(path, mime)
    key = storage.save(data)
    return StoredUpload(
        storage_key=str(key),
        original_name=_display_name(filename, mime),
        mime_type=mime,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        width=width,
        height=height,
    )
