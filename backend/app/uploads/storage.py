"""Streaming storage outside the web root (§14.9).

Uploads are copied in chunks to a temporary file while counting bytes (never held whole in
memory), checked, then moved to `UPLOAD_DIR/<uuid>` with mode 0640: readable by the Nginx
container through the shared group (it serves downloads from an `internal` location), never
world-readable. No user input is ever part of a path.
"""

from __future__ import annotations

import os
import re
import unicodedata
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Protocol

from app.uploads.errors import UploadTooLargeError

CHUNK = 64 * 1024
FILE_MODE = 0o640
_UNSAFE = re.compile(r"[^\w.\- ()]+", re.UNICODE)


class Readable(Protocol):
    async def read(self, size: int = -1) -> bytes: ...


def sanitize_name(name: str | None, fallback: str = "file") -> str:
    """Display-only file name: no paths, control or odd characters, at most 120 characters."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFKC", base)
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C")
    base = _UNSAFE.sub("_", base).strip(" ._") or fallback
    return base[:120]


class Storage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.tmp = self.root / ".incoming"

    def path_for(self, key: uuid.UUID) -> Path:
        return self.root / str(key)

    @asynccontextmanager
    async def receive(self, source: Readable, limit: int) -> AsyncIterator[Path]:
        """Stream `source` to a private temp file, enforcing `limit`; deleted afterwards."""
        self.tmp.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = self.tmp / uuid.uuid4().hex
        size = 0
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                while chunk := await source.read(CHUNK):
                    size += len(chunk)
                    if size > limit:
                        mb = limit // (1024 * 1024)
                        raise UploadTooLargeError(f"The file is larger than {mb} MB.")
                    out.write(chunk)
            yield path
        finally:
            path.unlink(missing_ok=True)

    def save(self, data: bytes) -> uuid.UUID:
        """Write final bytes under a new random key."""
        key = uuid.uuid4()
        self.root.mkdir(mode=0o750, parents=True, exist_ok=True)
        fd = os.open(self.path_for(key), os.O_WRONLY | os.O_CREAT | os.O_EXCL, FILE_MODE)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
        os.chmod(self.path_for(key), FILE_MODE)  # umask-independent
        return key

    def delete(self, key: uuid.UUID) -> None:
        self.path_for(key).unlink(missing_ok=True)
