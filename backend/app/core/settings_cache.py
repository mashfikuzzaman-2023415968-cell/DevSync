"""Process-local cache of the active platform settings (60 s), for hot paths like rate limits.

The table is admin-only under row-level security, so the active version is read
through the `active_settings()` SECURITY DEFINER function. If the database is
unreachable the last good copy (or the schema defaults) is used, so a DB blip
never disables rate limiting.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import column, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.schemas.platform_settings import PlatformSettingsValues

log = get_logger(__name__)
TTL_SECONDS = 60.0

_cache: dict[str, Any] = {"values": None, "version": 0, "loaded_at": 0.0}


async def active_settings(db: AsyncSession) -> PlatformSettingsValues:
    """Validated active settings, refreshed at most once per minute."""
    now = time.monotonic()
    cached = _cache["values"]
    if isinstance(cached, PlatformSettingsValues) and now - _cache["loaded_at"] < TTL_SECONDS:
        return cached
    try:
        stmt: Any = select(column("version"), column("values")).select_from(func.active_settings())
        row = (await db.execute(stmt)).mappings().first()
        values = (
            PlatformSettingsValues.model_validate(row["values"])
            if row
            else PlatformSettingsValues()
        )
        _cache.update(values=values, version=row["version"] if row else 0, loaded_at=now)
    except Exception as exc:  # any DB problem: keep serving the last good settings
        log.warning("settings_cache_refresh_failed", error=type(exc).__name__)
        if isinstance(cached, PlatformSettingsValues):
            return cached
        values = PlatformSettingsValues()
    return values


def clear() -> None:
    """Forget the cached copy (tests, settings changes)."""
    _cache.update(values=None, version=0, loaded_at=0.0)
