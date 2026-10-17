"""Authentication endpoints (spec §10.2 Auth). HTTP only: parse, call services, set cookies."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from app.api.deps import (
    DbSession,
    app_settings,
    now,
    rate_limit,
    redis_client,
    require,
    session_of,
)
from app.core import captcha, csrf
from app.core.auth_middleware import (
    clear_session_cookie,
    client_ip,
    csrf_cookie,
    session_cookie,
)
from app.core.authz import Principal
from app.core.config import Settings
from app.core.errors import AuthError
from app.core.security import derive_key
from app.core.sessions import SessionData
from app.schemas.auth import (
    AcceptedResponse,
    ChangePasswordRequest,
    CodeRequest,
    EmailTokenRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RecoveryCodesResponse,
    RegisterRequest,
    ResetPasswordRequest,
    SessionInfo,
    SessionList,
    TotpLoginRequest,
    TotpSetupResponse,
)
from app.schemas.common import error_responses
from app.services.auth import account, credentials, registration
from app.services.auth import login as login_service
from app.services.auth.common import AuthDeps

router = APIRouter(prefix="/auth", tags=["auth"])

SettingsDep = Annotated[Settings, Depends(app_settings)]
NO_CONTENT: dict[int | str, dict[str, Any]] = {204: {"description": "Done"}}


def _deps(db: DbSession, settings: Settings) -> AuthDeps:
    return AuthDeps(db=db, settings=settings, redis=redis_client())


def _require_session(request: Request) -> tuple[str, SessionData]:
    found = session_of(request)
    if found is None:
        raise AuthError
    return found


def _signed_in_response(
    body: dict[str, object], token: str, data: SessionData, status_code: int = 200
) -> JSONResponse:
    response = JSONResponse(body, status_code=status_code)
    max_age = int((data.expires_at - data.created_at).total_seconds())
    response.headers.append("set-cookie", session_cookie(token, max_age))
    response.headers.append("set-cookie", csrf_cookie(csrf.issue_token(data.csrf_secret)))
    return response


def _client(request: Request) -> login_service.ClientInfo:
    return login_service.ClientInfo(
        ip=client_ip(request.scope), user_agent=request.headers.get("user-agent")
    )


def _bypass(settings: Settings, payload: str | None) -> bool:
    return settings.DEVSYNC_ENV.value == "test" and payload == "test-bypass"


# --------------------------------------------------------------------------- CSRF


@router.get(
    "/csrf",
    summary="Issue a CSRF token cookie",
    status_code=204,
    responses={204: {"description": "Cookie `__Host-ds_csrf` set"}},
)
async def get_csrf(request: Request, settings: SettingsDep) -> Response:
    """Bound to the current session, or to the anonymous key for public forms."""
    found = session_of(request)
    key = found[1].csrf_secret if found else derive_key(settings.SECRET_KEY, "csrf-anonymous")
    response = Response(status_code=204)
    response.headers.append("set-cookie", csrf_cookie(csrf.issue_token(key)))
    return response


# --------------------------------------------------------------------------- registration


@router.post(
    "/register",
    summary="Create a client or developer account",
    status_code=202,
    response_model=AcceptedResponse,
    dependencies=[Depends(rate_limit("registration"))],
    responses={
        202: {
            "content": {"application/json": {"example": {"message": registration.UNIFORM_MESSAGE}}}
        },
        **error_responses(403, 422, 429),
    },
)
async def register(body: RegisterRequest, db: DbSession, settings: SettingsDep) -> AcceptedResponse:
    """Uniform answer whether or not the email/phone already exists (no enumeration)."""
    deps = _deps(db, settings)
    await captcha.verify(
        deps.redis, settings.CAPTCHA_HMAC_KEY, payload=body.captcha, honeypot=body.website,
        started_at_ms=body.started_at_ms, bypass=_bypass(settings, body.captcha),
    )  # fmt: skip
    await registration.register(
        deps, now(), display_name=body.display_name, email=str(body.email),
        phone=body.phone, password=body.password, role=body.role,
    )  # fmt: skip
    return AcceptedResponse(message=registration.UNIFORM_MESSAGE)


# --------------------------------------------------------------------------- login


@router.post(
    "/login",
    summary="Sign in with email and password",
    response_model=LoginResponse,
    responses={
        200: {
            "content": {
                "application/json": {"example": {"status": "SIGNED_IN", "redirect_to": "/client"}}
            }
        },
        **error_responses(401, 403, 422, 429),
        423: {"description": "Account temporarily locked"},
    },
)
async def login(
    body: LoginRequest, request: Request, db: DbSession, settings: SettingsDep
) -> JSONResponse:
    """Admins get `TOTP_REQUIRED` and a short-lived `pre_auth` token instead of a session."""
    result = await login_service.login(
        _deps(db, settings), now(),
        _client(request),
        email=str(body.email), password=body.password, captcha_payload=body.captcha,
        honeypot=body.website, started_at_ms=body.started_at_ms, return_to=body.return_to,
    )  # fmt: skip
    if isinstance(result, login_service.TotpChallenge):
        return JSONResponse(
            LoginResponse(status="TOTP_REQUIRED", pre_auth=result.pre_auth).model_dump()
        )
    status = "TOTP_SETUP_REQUIRED" if result.redirect_to == "/admin/setup-2fa" else "SIGNED_IN"
    answer = LoginResponse(status=status, redirect_to=result.redirect_to).model_dump()
    return _signed_in_response(answer, result.token, result.data)


@router.post(
    "/login/totp",
    summary="Second factor for admins",
    response_model=LoginResponse,
    responses={
        200: {
            "content": {
                "application/json": {"example": {"status": "SIGNED_IN", "redirect_to": "/admin"}}
            }
        },
        **error_responses(401, 403, 422, 429),
    },
)
async def login_totp(
    body: TotpLoginRequest, request: Request, db: DbSession, settings: SettingsDep
) -> JSONResponse:
    """A 6-digit TOTP code or one recovery code completes the admin sign-in."""
    result = await login_service.login_totp(
        _deps(db, settings), now(),
        _client(request),
        pre_auth=body.pre_auth, code=body.code, recovery_code=body.recovery_code,
        return_to=body.return_to,
    )  # fmt: skip
    answer = LoginResponse(status="SIGNED_IN", redirect_to=result.redirect_to).model_dump()
    return _signed_in_response(answer, result.token, result.data)


@router.post(
    "/logout",
    summary="Sign out of this device",
    status_code=204,
    responses={**NO_CONTENT, **error_responses(401, 403, 404)},
)
async def logout(
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("account.read"))],
) -> Response:
    """Ends the server-side session and clears the cookie."""
    await account.logout(_deps(db, settings), principal, _require_session(request), now())
    response = Response(status_code=204)
    response.headers.append("set-cookie", clear_session_cookie())
    return response


@router.post(
    "/logout-all",
    summary="Sign out of every device",
    status_code=204,
    responses={**NO_CONTENT, **error_responses(401, 403, 404)},
)
async def logout_all(
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("account.read"))],
) -> Response:
    """Revokes all sessions, including this one."""
    await account.logout_all(_deps(db, settings), principal, now())
    response = Response(status_code=204)
    response.headers.append("set-cookie", clear_session_cookie())
    return response


# --------------------------------------------------------------------------- sessions


@router.get(
    "/sessions",
    summary="List signed-in devices",
    response_model=SessionList,
    responses={
        200: {"content": {"application/json": {"example": {"items": []}}}},
        **error_responses(401, 403, 404),
    },
)
async def list_sessions(
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("session.manage"))],
) -> SessionList:
    """Device, address and last activity of each live session."""
    rows = await account.list_sessions(_deps(db, settings), principal, now())
    return SessionList(
        items=[
            SessionInfo(
                id=r.id,
                current=r.id == principal.session_id,
                ip=str(r.ip) if r.ip else None,
                user_agent=r.user_agent,
                created_at=r.created_at,
                last_seen_at=r.last_seen_at,
            )
            for r in rows
        ]
    )


@router.delete(
    "/sessions/{session_id}",
    summary="Sign out one device",
    status_code=204,
    responses={**NO_CONTENT, **error_responses(401, 403, 404, 422)},
)
async def revoke_session(
    session_id: uuid.UUID,
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("session.manage"))],
) -> Response:
    """Another user's session id answers 404."""
    await account.revoke_session(_deps(db, settings), principal, session_id, now())
    return Response(status_code=204)


# --------------------------------------------------------------------------- verification


@router.post(
    "/otp/send",
    summary="Send a phone verification code",
    status_code=204,
    dependencies=[Depends(rate_limit("otp_send"))],
    responses={**NO_CONTENT, **error_responses(401, 403, 404, 409, 429)},
)
async def otp_send(
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("account.verify"))],
) -> Response:
    """60-second cooldown between codes."""
    await registration.send_phone_otp(_deps(db, settings), principal, now())
    return Response(status_code=204)


@router.post(
    "/otp/verify",
    summary="Verify the phone code",
    status_code=204,
    dependencies=[Depends(rate_limit("otp_verify"))],
    responses={**NO_CONTENT, **error_responses(400, 401, 403, 404, 409, 422, 429)},
)
async def otp_verify(
    body: CodeRequest,
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("account.verify"))],
) -> Response:
    """Codes expire after 5 minutes and allow 5 attempts."""
    await registration.verify_phone_otp(_deps(db, settings), principal, body.code, now())
    return Response(status_code=204)


@router.post(
    "/email/verify",
    summary="Verify the email address from the link",
    status_code=204,
    responses={**NO_CONTENT, **error_responses(400, 403, 422, 429)},
)
async def email_verify(body: EmailTokenRequest, db: DbSession, settings: SettingsDep) -> Response:
    """Public: the token in the link is the proof."""
    await registration.verify_email(_deps(db, settings), body.token, now())
    return Response(status_code=204)


@router.post(
    "/email/resend",
    summary="Send a new verification email",
    status_code=204,
    dependencies=[Depends(rate_limit("email_resend"))],
    responses={**NO_CONTENT, **error_responses(401, 403, 404, 409, 429)},
)
async def email_resend(
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("account.verify"))],
) -> Response:
    """Older links stop working."""
    await registration.resend_verification_email(_deps(db, settings), principal, now())
    return Response(status_code=204)


# --------------------------------------------------------------------------- passwords


@router.post(
    "/password/forgot",
    summary="Request a password reset link",
    status_code=202,
    response_model=AcceptedResponse,
    dependencies=[Depends(rate_limit("password_reset"))],
    responses={
        202: {
            "content": {
                "application/json": {"example": {"message": credentials.UNIFORM_FORGOT_MESSAGE}}
            }
        },
        **error_responses(403, 422, 429),
    },
)
async def password_forgot(
    body: ForgotPasswordRequest, db: DbSession, settings: SettingsDep
) -> AcceptedResponse:
    """Same answer whether or not the email exists."""
    deps = _deps(db, settings)
    await captcha.verify(
        deps.redis, settings.CAPTCHA_HMAC_KEY, payload=body.captcha, honeypot=body.website,
        started_at_ms=body.started_at_ms, bypass=_bypass(settings, body.captcha),
    )  # fmt: skip
    await credentials.forgot_password(deps, str(body.email), now())
    return AcceptedResponse(message=credentials.UNIFORM_FORGOT_MESSAGE)


@router.post(
    "/password/reset",
    summary="Set a new password from the reset link",
    status_code=204,
    dependencies=[Depends(rate_limit("password_reset"))],
    responses={**NO_CONTENT, **error_responses(400, 403, 422, 429)},
)
async def password_reset(
    body: ResetPasswordRequest, db: DbSession, settings: SettingsDep
) -> Response:
    """Signs the user out of every device."""
    await credentials.reset_password(_deps(db, settings), body.token, body.new_password, now())
    response = Response(status_code=204)
    response.headers.append("set-cookie", clear_session_cookie())
    return response


@router.post(
    "/password/change",
    summary="Change password",
    status_code=204,
    responses={**NO_CONTENT, **error_responses(401, 403, 404, 422)},
)
async def password_change(
    body: ChangePasswordRequest,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("account.update"))],
) -> Response:
    """Other devices are signed out; this session gets a fresh token."""
    token, data = await credentials.change_password(
        _deps(db, settings), principal, _require_session(request),
        current_password=body.current_password, new_password=body.new_password, now=now(),
    )  # fmt: skip
    response = Response(status_code=204)
    response.headers.append(
        "set-cookie", session_cookie(token, int((data.expires_at - now()).total_seconds()))
    )
    response.headers.append("set-cookie", csrf_cookie(csrf.issue_token(data.csrf_secret)))
    return response


# --------------------------------------------------------------------------- admin 2FA


@router.post(
    "/totp/setup",
    summary="Start authenticator setup (admins)",
    response_model=TotpSetupResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "provisioning_uri": "otpauth://totp/DevSync:a@b",
                        "secret": "BASE32",
                    }
                }
            }
        },
        **error_responses(401, 403, 404),
    },
)
async def totp_setup(
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("totp.manage"))],
) -> TotpSetupResponse:
    """Replacing a confirmed authenticator needs step-up."""
    uri, secret = await credentials.totp_setup(_deps(db, settings), principal, now())
    return TotpSetupResponse(provisioning_uri=uri, secret=secret)


@router.post(
    "/totp/confirm",
    summary="Confirm the authenticator with a code (admins)",
    response_model=RecoveryCodesResponse,
    dependencies=[Depends(rate_limit("totp"))],
    responses={
        200: {"content": {"application/json": {"example": {"recovery_codes": ["k7f2-9qxm-4d"]}}}},
        **error_responses(400, 401, 403, 404, 409, 422, 429),
    },
)
async def totp_confirm(
    body: CodeRequest,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("totp.manage"))],
) -> JSONResponse:
    """Returns 10 single-use recovery codes, shown only once."""
    codes, token, data = await credentials.totp_confirm(
        _deps(db, settings), principal, _require_session(request), body.code, now()
    )
    return _signed_in_response({"recovery_codes": codes}, token, data)


@router.post(
    "/recovery-codes/regenerate",
    summary="Replace recovery codes (admins, step-up)",
    response_model=RecoveryCodesResponse,
    responses={
        200: {"content": {"application/json": {"example": {"recovery_codes": ["k7f2-9qxm-4d"]}}}},
        **error_responses(401, 403, 404),
    },
)
async def recovery_regenerate(
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("admin.access"))],
) -> RecoveryCodesResponse:
    """Old codes stop working."""
    codes = await credentials.regenerate_recovery_codes(_deps(db, settings), principal, now())
    return RecoveryCodesResponse(recovery_codes=codes)


@router.post(
    "/step-up",
    summary="Re-confirm TOTP for sensitive actions (admins)",
    status_code=204,
    dependencies=[Depends(rate_limit("totp"))],
    responses={**NO_CONTENT, **error_responses(401, 403, 404, 422, 429)},
)
async def step_up(
    body: CodeRequest,
    request: Request,
    db: DbSession,
    settings: SettingsDep,
    principal: Annotated[Principal, Depends(require("admin.access"))],
) -> Response:
    """Valid for 10 minutes; the session token is rotated."""
    token, data = await credentials.step_up(
        _deps(db, settings), principal, _require_session(request), body.code, now()
    )
    response = Response(status_code=204)
    response.headers.append(
        "set-cookie", session_cookie(token, int((data.expires_at - now()).total_seconds()))
    )
    response.headers.append("set-cookie", csrf_cookie(csrf.issue_token(data.csrf_secret)))
    return response
