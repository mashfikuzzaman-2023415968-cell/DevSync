"""Check for fastapi_error_handling_04: run the snippet for real; the marked option must equal the result."""

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

DB = {1: "pen"}

@app.get("/items/{item_id}")
def get_item(item_id: int):
    try:
        if item_id not in DB:
            raise HTTPException(status_code=404, detail="missing")
        return {"item": DB[item_id]}
    except Exception:
        raise HTTPException(status_code=500, detail="failed")
assert c.get("/items/1").status_code == 200

print(show(c.get("/items/2")))
'''


def check(ctx, q):
    ctx.expect_only(q, ctx.python(CODE))
