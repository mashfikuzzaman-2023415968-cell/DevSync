"""Check for fastapi_error_handling_06: run the snippet for real; the marked option must equal the result."""

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

@app.get("/search")
def search(q: str):
    return {"q": q}
r = c.get("/search")
assert r.status_code == 422

print(json.dumps(r.json()["detail"][0]["loc"]))
'''


def check(ctx, q):
    ctx.expect_only(q, ctx.python(CODE))
