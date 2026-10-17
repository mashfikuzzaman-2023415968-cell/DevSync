"""Platform settings service: read the active version, create validated new versions (§6.2).

Each change writes a new immutable version row and an audit entry in the same
transaction. Runs and reputation logs record the version they used.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import column, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.errors import SettingsValidationError
from app.models.foundation import PlatformSettings
from app.schemas.platform_settings import PlatformSettingsValues

MIN_REASON_LENGTH = 10
SETTINGS_LOCK_KEY = 0x0D5E7711  # arbitrary constant identifying the settings-version lock


def validate_settings(values: dict[str, Any]) -> PlatformSettingsValues:
    """Validate a settings document; raise SettingsValidationError with per-field messages."""
    try:
        return PlatformSettingsValues.model_validate(values)
    except ValidationError as exc:
        fields = {
            ".".join(str(p) for p in err["loc"]) or "values": err["msg"] for err in exc.errors()
        }
        raise SettingsValidationError("The settings are not valid.", fields=fields) from exc


async def get_active(session: AsyncSession) -> tuple[int, PlatformSettingsValues]:
    """Return (version, values) of the latest settings (via `active_settings()`, which works
    in every request context although the table itself is admin-only under RLS)."""
    stmt: Any = select(column("version"), column("values")).select_from(func.active_settings())
    row = (await session.execute(stmt)).mappings().first()
    if row is None:
        raise SettingsValidationError("No platform settings have been seeded.")
    return int(row["version"]), validate_settings(row["values"])


async def create_version(
    session: AsyncSession,
    values: dict[str, Any],
    *,
    reason: str,
    changed_by: uuid.UUID | None,
    actor_role: str | None = None,
) -> int:
    """Validate and store a new settings version (caller commits). Returns the new version."""
    if len(reason.strip()) < MIN_REASON_LENGTH:
        raise SettingsValidationError(
            "Please explain the change.", fields={"reason": "At least 10 characters"}
        )
    validated = validate_settings(values)
    # Serialize concurrent saves so two admins can't race for the same version number.
    await session.execute(select(func.pg_advisory_xact_lock(SETTINGS_LOCK_KEY)))
    current = (await session.execute(select(func.max(PlatformSettings.version)))).scalar_one()
    previous: dict[str, Any] | None = None
    if current is not None:
        previous = (
            await session.execute(
                select(PlatformSettings.values).where(PlatformSettings.version == current)
            )
        ).scalar_one()
    new_version = (current or 0) + 1
    document = validated.model_dump(mode="json")
    session.add(
        PlatformSettings(
            version=new_version, values=document, changed_by=changed_by, reason=reason.strip()
        )
    )
    await write_audit(
        session,
        action="settings.update",
        entity_type="platform_settings",
        entity_id=str(new_version),
        actor_id=changed_by,
        actor_role=actor_role,
        before=previous,
        after=document,
    )
    await session.flush()
    return new_version
