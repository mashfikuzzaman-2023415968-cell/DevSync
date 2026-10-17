"""Idempotency keys for money and job-creating endpoints (spec §10.1).

A client sends `Idempotency-Key: <uuid>`. The first request stores its response;
a repeat with the same body gets the stored response; a repeat with a different
body is a 409 (`IDEMPOTENCY_CONFLICT`). Keys are per user and kept 7 days.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, ErrorCode
from app.models.foundation import IdempotencyKey

RETENTION = timedelta(days=7)


class IdempotencyConflict(DomainError):  # noqa: N818
    """Same key reused with a different request."""

    code = ErrorCode.IDEMPOTENCY_CONFLICT


class InvalidIdempotencyKey(DomainError):  # noqa: N818
    """Missing or malformed key."""

    code = ErrorCode.BAD_REQUEST


def parse_key(raw: str | None) -> str:
    """Validate the header (a UUID); raise if missing or malformed."""
    if not raw:
        raise InvalidIdempotencyKey("An Idempotency-Key header is required.")
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise InvalidIdempotencyKey("Idempotency-Key must be a UUID.") from exc


def request_fingerprint(method: str, path: str, body: Any) -> bytes:
    """Stable hash of what the request asks for."""
    canonical = json.dumps(
        {"m": method.upper(), "p": path, "b": body}, sort_keys=True, default=str
    ).encode()
    return hashlib.sha256(canonical).digest()


@dataclass(frozen=True)
class StoredResponse:
    """A previously recorded response."""

    status_code: int
    body: dict[str, Any]


async def begin(
    db: AsyncSession, *, user_id: uuid.UUID, key: str, fingerprint: bytes, now: datetime
) -> StoredResponse | None:
    """Reserve the key. Returns the stored response for a replay, None for a first use."""
    inserted = await db.execute(
        insert(IdempotencyKey)
        .values(user_id=user_id, key=key, request_hash=fingerprint, expires_at=now + RETENTION)
        .on_conflict_do_nothing(constraint="uq_idempotency_keys_user_key")
        .returning(IdempotencyKey.id)
    )
    if inserted.scalar_one_or_none() is not None:
        return None
    existing = (
        await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
            )
        )
    ).scalar_one()
    # Constant-time comparison of the stored request digest (spec §16.7).
    if not hmac.compare_digest(existing.request_hash, fingerprint):
        raise IdempotencyConflict("This Idempotency-Key was already used for another request.")
    if existing.status_code is None or existing.response is None:
        raise IdempotencyConflict("The original request is still being processed.")
    return StoredResponse(status_code=existing.status_code, body=existing.response)


async def complete(
    db: AsyncSession, *, user_id: uuid.UUID, key: str, status_code: int, body: dict[str, Any]
) -> None:
    """Store the response for future replays (same transaction as the work)."""
    row = (
        await db.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
            )
        )
    ).scalar_one()
    row.status_code = status_code
    row.response = body
    await db.flush()
