"""Stored files: accepting uploads and handing out short-lived download URLs (spec §14.9).

`GET /files/{id}/download` authorizes through the `file_access` definer and redirects to a
signed `/files/blob/<key>` URL; that endpoint checks only the signature (it may be followed by an
`<img>` or a new tab) and answers with an `X-Accel-Redirect` so Nginx streams the bytes from its
`internal` location.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import NotFoundError
from app.models.profiles import FileKind, StoredFile
from app.repositories import profiles as repo
from app.services.context import Ctx
from app.uploads import signing
from app.uploads.pipeline import accept_upload
from app.uploads.storage import Readable, Storage, sanitize_name

INTERNAL_PREFIX = "/_protected_files/"
SERVABLE_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "application/pdf", "text/plain"}
)


def storage_for(settings: Settings) -> Storage:
    return Storage(settings.UPLOAD_DIR)


async def store_upload(
    ctx: Ctx, source: Readable, kind: FileKind, filename: str | None
) -> StoredFile:
    """Run the upload pipeline and record the file as attached (in the caller's transaction).

    If the transaction later fails, the bytes on disk have no row and the cleanup job removes
    them after 24 hours.
    """
    upload = await accept_upload(
        storage_for(ctx.settings),
        source,
        kind=kind,
        filename=filename,
        max_upload_bytes=ctx.settings.MAX_UPLOAD_MB * 1024 * 1024,
    )
    row = StoredFile(
        owner_id=ctx.uid,
        kind=kind,
        storage_key=uuid.UUID(upload.storage_key),
        original_name=upload.original_name,
        mime_type=upload.mime_type,
        size_bytes=upload.size_bytes,
        width=upload.width,
        height=upload.height,
        sha256=upload.sha256,
        attached_at=ctx.now,
    )
    await repo.add_file(ctx.db, row)
    return row


async def download_url(
    db: AsyncSession, settings: Settings, file_id: uuid.UUID, now: datetime
) -> str:
    """Signed 5-minute URL for a file the caller may see; others get 'not found'."""
    loc = await repo.file_access(db, file_id)
    if loc is None or loc.mime_type not in SERVABLE_TYPES:
        raise NotFoundError
    signed = signing.SignedFile(
        storage_key=str(loc.storage_key),
        mime_type=loc.mime_type,
        name=sanitize_name(loc.original_name),
        expires=signing.expiry(now),
    )
    return signing.sign_url(settings.SECRET_KEY, signed)


@dataclass(frozen=True)
class Blob:
    """What the blob endpoint tells Nginx to send."""

    accel_path: str
    mime_type: str
    name: str


def resolve_blob(
    settings: Settings,
    *,
    storage_key: uuid.UUID,
    mime_type: str,
    name: str,
    expires: int,
    signature: str,
    now: datetime,
) -> Blob:
    """Check a signed URL; a bad, tampered or expired one is 'not found'."""
    signed = signing.SignedFile(str(storage_key), mime_type, name, expires)
    if mime_type not in SERVABLE_TYPES or not signing.verify(
        settings.SECRET_KEY, signed, signature, now
    ):
        raise NotFoundError
    return Blob(f"{INTERNAL_PREFIX}{storage_key}", mime_type, sanitize_name(name))


ORPHAN_AGE = timedelta(hours=24)
INCOMING_AGE = timedelta(hours=1)


def _older_than(path: Path, cutoff: datetime) -> bool:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC) < cutoff
    except FileNotFoundError:
        return False


async def purge_orphans(db: AsyncSession, storage: Storage, now: datetime) -> dict[str, int]:
    """Worker job (SYSTEM context, §14.9): remove deleted files and uploads never attached for
    24 hours — both their rows and their bytes — plus bytes on disk that no row knows (a request
    that failed after storing) and stale temp files."""
    counts = {"rows": 0, "skipped": 0, "orphan_bytes": 0, "incoming": 0}
    cutoff = now - ORPHAN_AGE
    for f in await repo.purgeable_files(db, cutoff, limit=500):
        key = f.storage_key
        try:
            async with db.begin_nested():  # a row still referenced somewhere stays
                await repo.delete_row(db, f)
        except IntegrityError:
            counts["skipped"] += 1
            continue
        storage.delete(key)
        counts["rows"] += 1
    await db.commit()
    candidates: dict[uuid.UUID, Path] = {}
    for path in storage.root.iterdir() if storage.root.exists() else ():
        try:
            key = uuid.UUID(path.name)
        except ValueError:
            continue  # `.incoming` and anything that isn't ours
        if path.is_file() and _older_than(path, cutoff):
            candidates[key] = path
    known = await repo.known_storage_keys(db, list(candidates))
    for key, path in candidates.items():
        if key not in known:
            path.unlink(missing_ok=True)
            counts["orphan_bytes"] += 1
    for path in storage.tmp.iterdir() if storage.tmp.exists() else ():
        if path.is_file() and _older_than(path, now - INCOMING_AGE):
            path.unlink(missing_ok=True)
            counts["incoming"] += 1
    return counts
