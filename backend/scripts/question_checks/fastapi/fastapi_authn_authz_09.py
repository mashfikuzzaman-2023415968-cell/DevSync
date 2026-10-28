"""Check for fastapi_authn_authz_09: run the snippet for real; the marked option must equal the result."""

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

def current_user():
    raise HTTPException(status_code=401)

def require_role(role: str):
    def checker(user=Depends(current_user)):
        if user.role != role:
            raise HTTPException(status_code=403)
        return user
    return checker

@app.get("/admin")
def admin_panel(user=Depends(require_role)):
    return {"ok": True}

print(show(c.get("/admin?role=x")))
"""


def check(ctx, q):
    ctx.expect_only(q, ctx.python(CODE))
