"""Request/response models for profiles, portfolio, evidence and files (spec §7.2, §10.2).

Requests reject unknown fields, so `user_id`, `status`, `reviewed_by`, `position` (outside the
reorder endpoint) and the like can never be set by a client. Bounds mirror the database checks.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, BeforeValidator, Field, field_validator

from app.schemas.common import StrictRequest

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # keeps \t \n \r in long text
LINE_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
GITHUB_USERNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
HTTPS_URL = re.compile(r"^https://[A-Za-z0-9.-]+(?::\d{1,5})?(?:/[^\s<>\"']*)?$")

SkillDomainName = Literal[
    "FRONTEND", "BACKEND", "DATABASE", "MOBILE", "DESIGN", "TESTING", "DEVOPS", "DATA"
]
VisibilityName = Literal["PUBLIC", "CLIENTS_ONLY"]
VerificationName = Literal["PENDING", "VERIFIED", "REJECTED"]


def _line(value: object) -> object:
    """One-line text: no control characters, NFC, trimmed (before the length checks run)."""
    if not isinstance(value, str):
        return value
    return unicodedata.normalize("NFC", LINE_CONTROL.sub("", value)).strip()


def _text(value: object) -> object:
    """Multi-line text: control characters except tab/newline removed, NFC, trimmed."""
    if not isinstance(value, str):
        return value
    return unicodedata.normalize("NFC", CONTROL.sub("", value)).strip()


def _https(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if len(value) > 300 or not HTTPS_URL.match(value):  # noqa: PLR2004 - spec §7.2 bound
        raise ValueError("Use a full https:// address (at most 300 characters).")
    return value


def _github(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not GITHUB_USERNAME.match(value):
        raise ValueError("Use a GitHub username (letters, digits and single hyphens).")
    return value


@lru_cache(maxsize=1)
def _zones() -> frozenset[str]:
    return frozenset(available_timezones())


def _timezone(value: str) -> str:
    if value not in _zones():
        raise ValueError("Use a time zone such as Asia/Dhaka.")
    return value


def _unique(values: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(values)) != len(values):
        raise ValueError("Each item may appear only once.")
    return values


Line120 = Annotated[str, BeforeValidator(_line), Field(max_length=120)]
Title = Annotated[str, BeforeValidator(_line), Field(min_length=1, max_length=120)]
SourceName = Annotated[str, BeforeValidator(_line), Field(min_length=1, max_length=80)]
Text2000 = Annotated[str, BeforeValidator(_text), Field(max_length=2000)]
HttpsUrl = Annotated[str | None, AfterValidator(_https)]
SkillIds = Annotated[list[uuid.UUID], AfterValidator(_unique), Field(max_length=8)]


# --------------------------------------------------------------------------- skills


class SkillOut(BaseModel):
    """One entry of the skill taxonomy."""

    id: uuid.UUID
    name: str
    domain: SkillDomainName


class DeveloperSkillOut(BaseModel):
    """A skill on a developer's profile with the self-assessed level (1–5)."""

    skill_id: uuid.UUID
    name: str
    domain: SkillDomainName
    self_level: int


class SkillLevel(StrictRequest):
    """One claimed skill."""

    skill_id: uuid.UUID
    self_level: int = Field(ge=1, le=5)


class SkillsUpdate(StrictRequest):
    """Replace the developer's skill list (at most 20 skills, each once)."""

    skills: list[SkillLevel] = Field(max_length=20)

    @field_validator("skills")
    @classmethod
    def _distinct(cls, value: list[SkillLevel]) -> list[SkillLevel]:
        _unique([s.skill_id for s in value])
        return value


# --------------------------------------------------------------------------- developer profile


class DeveloperProfileOut(BaseModel):
    """The caller's own developer profile."""

    headline: str
    bio: str
    hours_per_week: int
    github_username: str | None
    timezone: str
    visibility: VisibilityName
    skills: list[DeveloperSkillOut]
    updated_at: datetime | None


class DeveloperProfileUpdate(StrictRequest):
    """Partial update; omitted fields stay as they are."""

    headline: Line120 | None = None
    bio: Text2000 | None = None
    hours_per_week: int | None = Field(default=None, ge=1, le=80)
    github_username: Annotated[str | None, AfterValidator(_github)] = Field(
        default=None, max_length=39
    )
    timezone: Annotated[str, AfterValidator(_timezone)] | None = Field(default=None, max_length=64)
    visibility: VisibilityName | None = None


# --------------------------------------------------------------------------- client profile


class ClientProfileOut(BaseModel):
    """The caller's own client (organisation) profile."""

    organization: str
    description: str
    website: str | None
    updated_at: datetime | None


class ClientProfileUpdate(StrictRequest):
    """Partial update; omitted fields stay as they are; an empty website clears it."""

    organization: Line120 | None = None
    description: Text2000 | None = None
    website: HttpsUrl = Field(default=None, max_length=300)


# --------------------------------------------------------------------------- files


class FileOut(BaseModel):
    """Metadata of a stored file (download through `GET /files/{id}/download`)."""

    id: uuid.UUID
    name: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None


# --------------------------------------------------------------------------- portfolio


class PortfolioImageOut(BaseModel):
    """An image of a portfolio item."""

    id: uuid.UUID
    file: FileOut
    position: int


class PortfolioItemOut(BaseModel):
    """A portfolio item with its images in order."""

    id: uuid.UUID
    title: str
    description: str
    url: str | None
    skill_ids: list[uuid.UUID]
    position: int
    images: list[PortfolioImageOut]


class PortfolioItemCreate(StrictRequest):
    """A new portfolio item (added at the end; at most 20 per developer)."""

    title: Title
    description: Text2000 = ""
    url: HttpsUrl = Field(default=None, max_length=300)
    skill_ids: SkillIds = Field(default_factory=list)


class PortfolioItemUpdate(StrictRequest):
    """Partial update of a portfolio item."""

    title: Title | None = None
    description: Text2000 | None = None
    url: HttpsUrl = Field(default=None, max_length=300)
    skill_ids: SkillIds | None = None


class PortfolioReorder(StrictRequest):
    """Every portfolio item id, in the new order."""

    ids: Annotated[list[uuid.UUID], AfterValidator(_unique)] = Field(min_length=1, max_length=20)


# --------------------------------------------------------------------------- evidence


class CertificateOut(BaseModel):
    """A certificate and its verification status."""

    id: uuid.UUID
    title: str
    issuer: str
    file: FileOut
    status: VerificationName
    reason: str | None
    created_at: datetime


class CertificateUpdate(StrictRequest):
    """Correct the title or issuer while the certificate is still pending."""

    title: Title | None = None
    issuer: Title | None = None


class ExternalReviewOut(BaseModel):
    """A review from another platform and its verification status."""

    id: uuid.UUID
    source: str
    rating_norm: Decimal = Field(description="Rating scaled to 0–1 (3 decimals).")
    project_date: date
    file: FileOut
    status: VerificationName
    reason: str | None
    created_at: datetime


# --------------------------------------------------------------------------- public profile


class PublicSkill(BaseModel):
    """A claimed skill on a public profile."""

    skill_id: uuid.UUID
    name: str
    domain: SkillDomainName
    self_level: int


class VerifiedScore(BaseModel):
    """The latest verified test score per skill."""

    skill_id: uuid.UUID
    name: str
    score: Decimal
    at: datetime


class PublicPortfolioItem(BaseModel):
    """A portfolio item as others see it."""

    id: uuid.UUID
    title: str
    description: str
    url: str | None
    skill_ids: list[uuid.UUID]
    image_ids: list[uuid.UUID]


class PublicCertificate(BaseModel):
    """A verified certificate."""

    title: str
    issuer: str


class DeveloperPublicProfile(BaseModel):
    """What others may see of a developer (never email or phone)."""

    id: uuid.UUID
    display_name: str
    member_since: datetime
    headline: str
    bio: str
    hours_per_week: int
    github_username: str | None
    visibility: VisibilityName
    skills: list[PublicSkill]
    verified_scores: list[VerifiedScore]
    portfolio: list[PublicPortfolioItem]
    certificates: list[PublicCertificate]
