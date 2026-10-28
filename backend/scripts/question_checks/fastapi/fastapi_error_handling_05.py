"""Check for fastapi_error_handling_05: run the snippet for real; the marked option must equal the result."""

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

@app.exception_handler(HTTPException)
async def custom(request, exc):
    return JSONResponse({"custom": exc.detail}, status_code=exc.status_code)

@app.get("/boom")
def boom():
    raise HTTPException(status_code=418, detail="teapot")
assert c.get("/boom").json() == {"custom": "teapot"}  # the handler does work for FastAPI HTTPException
r = c.get("/no-such-route")
assert r.status_code == 404

print(json.dumps(r.json()))
"""


def check(ctx, q):
    ctx.expect_only(q, ctx.python(CODE))
