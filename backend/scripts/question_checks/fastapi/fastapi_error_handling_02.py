"""Check for fastapi_error_handling_02: run the snippet for real; the marked option must equal the result."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import json
from fastapi import FastAPI, HTTPException, Header, Query, Depends, APIRouter
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

app = FastAPI()
c = TestClient(app)

def show(r):
    return json.dumps(r.json()) if r.status_code == 200 else f"Status {r.status_code}"

@app.post("/users")
def create_user():
    raise HTTPException(status_code=409, detail={"code": "duplicate"})
r = c.post("/users")
assert r.status_code == 409

print(json.dumps(r.json()))
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    ctx.expect_only(q, ctx.python(CODE))
