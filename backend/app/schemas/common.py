"""Shared response envelopes used by every endpoint (spec §10.4 contract-first API)."""

from __future__ import annotations

import types
from datetime import date
from typing import Annotated, Any, Generic, Literal, TypeVar, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.core.errors import ErrorCode


def has_nul(value: object) -> bool:
    """True if a string, or any string inside a list, tuple or dict, contains a NUL character."""
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, (list, tuple)):
        return any(has_nul(item) for item in value)
    if isinstance(value, dict):
        return any(has_nul(key) or has_nul(item) for key, item in value.items())
    return False


def _leaf_types(annotation: object) -> set[object]:
    """The plain types a field annotation allows (`int | None` gives int and NoneType). Anything
    unusual gives `object`, which the callers treat as "allow anything"."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return _leaf_types(get_args(annotation)[0])
    if origin is Union or origin is types.UnionType:
        return set().union(*(_leaf_types(arg) for arg in get_args(annotation)))
    if origin is Literal:
        return {type(arg) for arg in get_args(annotation)}
    if origin is not None:
        return {origin}  # list, dict, ...: the container itself
    return {annotation} if isinstance(annotation, type) else {object}


# Pydantic's own date and time types are classes of their own, not subclasses of `date`.
_DATE_TYPE_NAMES = frozenset(
    {"AwareDatetime", "NaiveDatetime", "PastDate", "FutureDate", "PastDatetime", "FutureDatetime"}
)


def _is_date_type(kind: object) -> bool:
    return isinstance(kind, type) and (issubclass(kind, date) or kind.__name__ in _DATE_TYPE_NAMES)


def wrong_json_type(value: object, annotation: object) -> bool:
    """True for the two coercions pydantic allows but the API contract does not: a true/false value
    in a field that is not boolean (`false` would become 0), and a number in a date field (`0`
    would become 1970-01-01). Everything else is left to the field's own rules."""
    if value is None:
        return False
    kinds = _leaf_types(annotation)
    if object in kinds:
        return False
    if isinstance(value, bool):
        return bool not in kinds
    if isinstance(value, (int, float)):
        takes_date = any(_is_date_type(k) for k in kinds)
        takes_number = any(isinstance(k, type) and issubclass(k, (int, float)) for k in kinds)
        return takes_date and not takes_number
    return False


class StrictRequest(BaseModel):
    """Base for request bodies: unknown fields are rejected (mass-assignment defence, §14.5).

    A true/false value where a number or text is expected, and a number where a date is expected,
    are refused with a 422 instead of being coerced (see `wrong_json_type`).

    A NUL character left in any field is refused with a 422: PostgreSQL cannot store it, and it
    would otherwise come back as a 500. This runs after each field's own rules, so fields that
    clean their text (the profile schemas drop control characters) or that must be well formed
    (an email) behave exactly as before."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("*", mode="before")
    @classmethod
    def _refuse_wrong_json_type(cls, value: Any, info: ValidationInfo) -> Any:
        field = cls.model_fields.get(info.field_name or "")
        if field is not None and wrong_json_type(value, field.annotation):
            raise PydanticCustomError("json_type", "That isn't the right kind of value here.")
        return value

    @field_validator("*", mode="after")
    @classmethod
    def _refuse_nul_character(cls, value: Any) -> Any:
        if has_nul(value):
            raise PydanticCustomError("nul_character", "Text can't contain a NUL character.")
        return value


class ErrorDetail(BaseModel):
    """Body of the uniform error envelope."""

    code: ErrorCode
    message: str
    fields: dict[str, str] | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """`{"error": {code, message, fields?, request_id}}` for every 4xx/5xx response."""

    error: ErrorDetail


class ValidationErrorDetail(ErrorDetail):
    """422 body: `fields` maps each invalid field path to a message."""

    fields: dict[str, str] = Field(default_factory=dict)


class ValidationErrorResponse(BaseModel):
    """422 envelope."""

    error: ValidationErrorDetail


class StateTransitionErrorDetail(ErrorDetail):
    """409 INVALID_STATE body with the current state and what is allowed from it."""

    current_state: str
    allowed_actions: list[str]


class StateTransitionError(BaseModel):
    """409 envelope for invalid state transitions."""

    error: StateTransitionErrorDetail


T = TypeVar("T")


# Generic[T] instead of PEP 695 `class Page[T]` so Semgrep can parse this module.
class Page(BaseModel, Generic[T]):  # noqa: UP046
    """Cursor page `{items, next_cursor}` (limit ≤ 100, default 20)."""

    items: list[T]
    next_cursor: str | None = None


class JobAccepted(BaseModel):
    """202 body for endpoints that enqueue background work."""

    job_id: str
    status: str
    progress: int = Field(ge=0, le=100)


def error_responses(*statuses: int) -> dict[int | str, dict[str, object]]:
    """OpenAPI `responses=` entries with the error envelope and an example per status."""
    examples: dict[int, tuple[ErrorCode, str]] = {
        400: (ErrorCode.BAD_REQUEST, "The request could not be understood."),
        401: (ErrorCode.UNAUTHENTICATED, "Please sign in to continue."),
        403: (ErrorCode.ROLE_NOT_ALLOWED, "Your account can't do this."),
        404: (ErrorCode.NOT_FOUND, "We couldn't find that."),
        409: (ErrorCode.INVALID_STATE, "This can't be done in the current state."),
        413: (ErrorCode.PAYLOAD_TOO_LARGE, "The request is too large."),
        422: (ErrorCode.VALIDATION_ERROR, "Some fields need attention."),
        429: (ErrorCode.RATE_LIMITED, "Too many requests. Please wait and try again."),
        503: (ErrorCode.DEPENDENCY_UNAVAILABLE, "A service we depend on is unavailable."),
    }
    out: dict[int | str, dict[str, object]] = {}
    for status in statuses:
        code, message = examples[status]
        model: type[BaseModel] = ValidationErrorResponse if status == 422 else ErrorResponse  # noqa: PLR2004
        out[status] = {
            "model": model,
            "description": message,
            "content": {
                "application/json": {
                    "example": {
                        "error": {"code": code.value, "message": message, "request_id": "req_123"}
                    }
                }
            },
        }
    return out


def version_conflict_response(message: str) -> dict[int | str, dict[str, object]]:
    """The 409 entry for an `If-Match` update whose version is stale (§10.1)."""
    return {
        409: {
            "model": ErrorResponse,
            "description": "The resource changed since it was loaded (stale If-Match), or its "
            "state does not allow the change.",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": ErrorCode.VERSION_CONFLICT.value,
                            "message": message,
                            "request_id": "req_123",
                        }
                    }
                }
            },
        }
    }
