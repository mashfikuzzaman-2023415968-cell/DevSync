"""Developer SMS inbox (OTP sandbox): the texts DevSync "sent", for demos and development.

Mounted by `create_app` only when `Settings.sms_sandbox_enabled` (development, test, the offline
demo stack) and left out of the OpenAPI document. Anywhere else the routes do not exist, and
`assert_no_sandbox_routes` refuses to start if one does. It needs no sign-in, because the first
code is read before an account exists; it holds only codes sent in those environments. The same
switch mounts the quick sign-in tab's two routes (`/accounts`, `/sign-in`, see
`services/auth/demo_signin.py` for how narrow they are).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api.deps import DbSession, app_settings, now, redis_client
from app.core import csrf
from app.core.auth_middleware import client_ip, csrf_cookie, session_cookie
from app.core.config import Settings
from app.schemas.sms_sandbox import (
    DemoAccount,
    DemoAccountList,
    DemoSignInRequest,
    DemoSignInResponse,
    SandboxSmsList,
)
from app.services import sms_sandbox
from app.services.auth import demo_signin
from app.services.auth import login as login_service
from app.services.auth.common import AuthDeps

SANDBOX_PREFIX = "/dev-sandbox"

router = APIRouter(prefix=SANDBOX_PREFIX, tags=["dev-sandbox"], include_in_schema=False)


@router.get("/sms", response_model=SandboxSmsList)
async def list_sms(
    redis: Annotated[Redis, Depends(redis_client)],
    phone: Annotated[str | None, Query(max_length=20, pattern=r"^\+?[0-9 ]*$")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SandboxSmsList:
    """Texts sent so far, newest first; `phone` filters by number."""
    return await sms_sandbox.list_messages(redis, phone, limit)


@router.delete("/sms", status_code=204)
async def clear_sms(redis: Annotated[Redis, Depends(redis_client)]) -> Response:
    """Empty the inbox."""
    await sms_sandbox.clear_messages(redis)
    return Response(status_code=204)


@router.get("/accounts", response_model=DemoAccountList)
async def list_accounts() -> DemoAccountList:
    """The seeded demo clients and developers the quick sign-in tab offers."""
    found = await demo_signin.list_accounts()
    return DemoAccountList(
        accounts=[DemoAccount(email=a.email, name=a.name, role=a.role) for a in found]
    )


@router.post("/sign-in", response_model=DemoSignInResponse)
async def quick_sign_in(
    body: DemoSignInRequest,
    request: Request,
    db: DbSession,
    settings: Annotated[Settings, Depends(app_settings)],
) -> JSONResponse:
    """Start a session for one seeded demo account (never an administrator)."""
    result = await demo_signin.sign_in(
        AuthDeps(db=db, settings=settings, redis=redis_client()),
        now(),
        login_service.ClientInfo(
            ip=client_ip(request.scope), user_agent=request.headers.get("user-agent")
        ),
        email=body.email,
    )
    response = JSONResponse(DemoSignInResponse(redirect_to=result.redirect_to).model_dump())
    max_age = int((result.data.expires_at - result.data.created_at).total_seconds())
    response.headers.append("set-cookie", session_cookie(result.token, max_age))
    response.headers.append("set-cookie", csrf_cookie(csrf.issue_token(result.data.csrf_secret)))
    return response
