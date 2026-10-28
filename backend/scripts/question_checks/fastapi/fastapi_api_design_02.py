"""Check for fastapi_api_design_02: run the snippet for real; the marked option must equal the result."""

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

@app.get("/items")
def list_items(tag: list[str] = Query(default=[])):
    return tag

print(show(c.get("/items?tag=a&tag=b")))
"""


def check(ctx, q):
    ctx.expect_only(q, ctx.python(CODE))
