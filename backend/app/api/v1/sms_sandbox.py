"""Developer SMS inbox (OTP sandbox): the texts DevSync "sent", for demos and development.

Mounted by `create_app` only when `Settings.sms_sandbox_enabled` (development, test, the offline
demo stack) and left out of the OpenAPI document. Anywhere else the routes do not exist, and
`assert_no_sandbox_routes` refuses to start if one does. It needs no sign-in, because the first
code is read before an account exists; it holds only codes sent in those environments.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from redis.asyncio import Redis

from app.api.deps import redis_client
from app.schemas.sms_sandbox import SandboxSmsList
from app.services import sms_sandbox

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
