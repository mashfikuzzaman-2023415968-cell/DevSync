"""Domain error codes, their HTTP mapping and the safe exception handlers (spec §10.1).

Responses never contain stack traces, SQL, other users' ids, or whether an
account exists. Unknown exceptions become a generic 500 with only a request id;
the full trace is logged server-side.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match

from app.core.logging import get_logger, request_id_var

log = get_logger(__name__)


class ErrorCode(StrEnum):
    """Every domain error code the API can return (extended by later phases)."""

    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    ROLE_NOT_ALLOWED = "ROLE_NOT_ALLOWED"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INVALID_STATE = "INVALID_STATE"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_SETTINGS = "INVALID_SETTINGS"
    CSRF_FAILED = "CSRF_FAILED"
    CAPTCHA_FAILED = "CAPTCHA_FAILED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    TOTP_REQUIRED = "TOTP_REQUIRED"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    TOKEN_INVALID = "TOKEN_INVALID"
    ALREADY_VERIFIED = "ALREADY_VERIFIED"
    PASSWORD_REJECTED = "PASSWORD_REJECTED"


STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.BAD_REQUEST: 400,
    ErrorCode.UNAUTHENTICATED: 401,
    ErrorCode.ROLE_NOT_ALLOWED: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.METHOD_NOT_ALLOWED: 405,
    ErrorCode.INVALID_STATE: 409,
    ErrorCode.VERSION_CONFLICT: 409,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.INVALID_SETTINGS: 422,
    ErrorCode.CSRF_FAILED: 403,
    ErrorCode.CAPTCHA_FAILED: 403,
    ErrorCode.INVALID_CREDENTIALS: 401,
    ErrorCode.VERIFICATION_REQUIRED: 403,
    ErrorCode.TOTP_REQUIRED: 401,
    ErrorCode.STEP_UP_REQUIRED: 403,
    ErrorCode.TOKEN_INVALID: 400,
    ErrorCode.ALREADY_VERIFIED: 409,
    ErrorCode.PASSWORD_REJECTED: 422,
    ErrorCode.ACCOUNT_LOCKED: 423,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
    ErrorCode.TIMEOUT: 504,
}

SAFE_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.BAD_REQUEST: "The request could not be understood.",
    ErrorCode.UNAUTHENTICATED: "Please sign in to continue.",
    ErrorCode.ROLE_NOT_ALLOWED: "Your account can't do this.",
    ErrorCode.NOT_FOUND: "We couldn't find that.",
    ErrorCode.METHOD_NOT_ALLOWED: "This action isn't supported here.",
    ErrorCode.PAYLOAD_TOO_LARGE: "The request is too large.",
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: "Send the request body as JSON.",
    ErrorCode.VALIDATION_ERROR: "Some fields need attention.",
    ErrorCode.RATE_LIMITED: "Too many requests. Please wait and try again.",
    ErrorCode.INTERNAL_ERROR: "Something went wrong on our side. Please try again.",
    ErrorCode.DEPENDENCY_UNAVAILABLE: "A service we depend on is unavailable. Please try again.",
    ErrorCode.TIMEOUT: "The request took too long. Please try again.",
    ErrorCode.CSRF_FAILED: "Your session form expired. Refresh the page and try again.",
    ErrorCode.CAPTCHA_FAILED: "Please complete the verification check again.",
    ErrorCode.INVALID_CREDENTIALS: "Email or password is incorrect.",
    ErrorCode.VERIFICATION_REQUIRED: "Verify your phone and email to continue.",
    ErrorCode.TOTP_REQUIRED: "Enter the code from your authenticator app.",
    ErrorCode.STEP_UP_REQUIRED: "Confirm with your authenticator code to continue.",
    ErrorCode.TOKEN_INVALID: "This link or code is invalid or has expired.",
    ErrorCode.ALREADY_VERIFIED: "This is already verified.",
}


class DomainError(Exception):
    """Base class for errors that services raise and the API maps to safe responses."""

    code: ErrorCode = ErrorCode.BAD_REQUEST

    def __init__(
        self,
        message: str | None = None,
        *,
        code: ErrorCode | None = None,
        fields: dict[str, str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if code is not None:
            self.code = code
        self.message = message or SAFE_MESSAGES.get(self.code, "Request failed.")
        self.fields = fields
        self.extra = extra or {}
        super().__init__(self.message)

    @property
    def status_code(self) -> int:
        """HTTP status for this error's code."""
        return STATUS_BY_CODE[self.code]


class NotFoundError(DomainError):
    """Resource missing or not visible to the caller (never reveals which, §14.5)."""

    code = ErrorCode.NOT_FOUND


class InvalidStateTransition(DomainError):  # noqa: N818 - name fixed by spec §8
    """A state machine transition that is not allowed (→ 409 INVALID_STATE)."""

    code = ErrorCode.INVALID_STATE

    def __init__(
        self, current_state: str, allowed_actions: list[str], message: str | None = None
    ) -> None:
        super().__init__(
            message or f"This can't be done while the item is {current_state.lower()}.",
            extra={"current_state": current_state, "allowed_actions": allowed_actions},
        )


class AuthError(DomainError):
    """Authentication failed (401) — message is uniform so accounts can't be enumerated."""

    code = ErrorCode.UNAUTHENTICATED


class ForbiddenError(DomainError):
    """Signed in but the role may not do this (403)."""

    code = ErrorCode.ROLE_NOT_ALLOWED


class SettingsValidationError(DomainError):
    """Platform settings failed validation (§6.2)."""

    code = ErrorCode.INVALID_SETTINGS


def error_body(
    code: ErrorCode,
    message: str,
    fields: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the uniform error envelope `{"error": {...}}`."""
    error: dict[str, Any] = {"code": code.value, "message": message}
    if fields:
        error["fields"] = fields
    if extra:
        error.update(extra)
    error["request_id"] = request_id_var.get()
    return {"error": error}


def error_response(
    code: ErrorCode,
    message: str | None = None,
    *,
    fields: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """JSONResponse with the uniform envelope and `Cache-Control: no-store`."""
    body = error_body(code, message or SAFE_MESSAGES.get(code, "Request failed."), fields, extra)
    all_headers = {"Cache-Control": "no-store", **(headers or {})}
    return JSONResponse(body, status_code=STATUS_BY_CODE[code], headers=all_headers)


_HTTP_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.BAD_REQUEST,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.ROLE_NOT_ALLOWED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.DEPENDENCY_UNAVAILABLE,
}


def _validation_fields(exc: RequestValidationError) -> dict[str, str]:
    """Turn Pydantic errors into `{field_path: message}` without echoing input values."""
    fields: dict[str, str] = {}
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        fields[".".join(loc) or "body"] = str(err.get("msg", "Invalid value"))
    return fields


async def _domain_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):  # registered for this type only
        raise TypeError(type(exc).__name__)
    retry_after = getattr(exc, "retry_after", None)
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return error_response(
        exc.code, exc.message, fields=exc.fields, extra=exc.extra, headers=headers
    )


async def _validation_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):  # registered for this type only
        raise TypeError(type(exc).__name__)
    return error_response(ErrorCode.VALIDATION_ERROR, fields=_validation_fields(exc))


_HTTP_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


def _allowed_methods(request: Request) -> str | None:
    """Every method some route serves at this path (a path may be split across routes)."""
    router = getattr(request.app, "router", None)
    allowed = []
    for method in _HTTP_METHODS:
        probe = {**request.scope, "method": method}
        for route in getattr(router, "routes", []):
            match, _ = route.matches(probe)
            if match is Match.FULL:
                allowed.append(method)
                break
    return ", ".join(allowed) or None


async def _http_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):  # registered for this type only
        raise TypeError(type(exc).__name__)
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code, ErrorCode.BAD_REQUEST)
    headers = dict(exc.headers) if exc.headers else {}
    if exc.status_code == 405:  # noqa: PLR2004
        allow = _allowed_methods(_request)
        if allow:
            headers["Allow"] = allow
    return error_response(code, headers=headers or None)


async def _unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", exc_info=exc)
    return error_response(ErrorCode.INTERNAL_ERROR)


def install_exception_handlers(app: FastAPI) -> None:
    """Register the safe handlers (middleware step 10, §14.10)."""
    app.add_exception_handler(DomainError, _domain_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
