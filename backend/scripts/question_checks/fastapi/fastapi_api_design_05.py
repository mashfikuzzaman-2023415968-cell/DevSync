"""Check for fastapi_api_design_05: run the snippet for real; the marked option must equal the result."""

CODE = r'''
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

router = APIRouter(prefix="/items")

@router.get("/")
def list_items():
    return []

app.include_router(router)
r = c.get("/items", follow_redirects=False)
assert r.headers["location"].endswith("/items/")

print("Status 307 redirect to /items/" if r.status_code == 307 else show(r))
'''


def check(ctx, q):
    ctx.expect_only(q, ctx.python(CODE))
