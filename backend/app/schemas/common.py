"""Shared response envelopes used by every endpoint (spec §10.4 contract-first API)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.core.errors import ErrorCode


class StrictRequest(BaseModel):
    """Base for request bodies: unknown fields are rejected (mass-assignment defence, §14.5)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


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


class Page[T](BaseModel):
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
