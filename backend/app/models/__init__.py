"""SQLAlchemy models (spec §7). Importing this package registers every table on `Base.metadata`."""

from app.models.foundation import AuditLog, IdempotencyKey, Job, JobStatus, PlatformSettings
from app.models.identity import (
    DeviceSeen,
    EmailOutbox,
    EmailToken,
    EmailTokenPurpose,
    Notification,
    OtpCode,
    OtpPurpose,
    OutboxStatus,
    RecoveryCode,
    Session,
    TotpCredential,
    User,
    UserRole,
    UserStatus,
)

__all__ = [
    "AuditLog",
    "DeviceSeen",
    "EmailOutbox",
    "EmailToken",
    "EmailTokenPurpose",
    "IdempotencyKey",
    "Job",
    "JobStatus",
    "Notification",
    "OtpCode",
    "OtpPurpose",
    "OutboxStatus",
    "PlatformSettings",
    "RecoveryCode",
    "Session",
    "TotpCredential",
    "User",
    "UserRole",
    "UserStatus",
]
