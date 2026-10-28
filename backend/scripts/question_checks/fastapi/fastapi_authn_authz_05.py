"""Check for fastapi_authn_authz_05: run the snippet for real; the marked option must equal the result."""

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

oauth2 = OAuth2PasswordBearer(tokenUrl="login")

@app.get("/me")
def me(token: str = Depends(oauth2)):
    return {"token": token}
assert c.get("/me", headers={"Authorization": "Bearer abc"}).json() == {"token": "abc"}

print(show(c.get("/me")))
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    ctx.expect_only(q, ctx.python(CODE))
