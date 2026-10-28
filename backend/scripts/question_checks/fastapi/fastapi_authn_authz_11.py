"""Check for fastapi_authn_authz_11: run the snippet for real; the marked option must equal the result."""

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

class Order(BaseModel):
    qty: int

@app.post("/orders")
def create(order: Order, token: str = Depends(oauth2)):
    return {"qty": order.qty}
assert c.post("/orders", json={"qty": "many"}, headers={"Authorization": "Bearer t"}).status_code == 422

print(show(c.post("/orders", json={"qty": "many"})))
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    ctx.expect_only(q, ctx.python(CODE))
