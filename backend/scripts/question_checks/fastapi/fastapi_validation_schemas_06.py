"""Check for fastapi_validation_schemas_06: run the snippet for real; the marked option must equal the result."""

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

class Item(BaseModel):
    name: str
    price: int

@app.post("/items")
def create(item: Item):
    return item

print(show(c.post("/items", json={"name": "pen", "price": 5, "discount": 50})))
'''


def check(ctx, q):
    ctx.expect_only(q, ctx.python(CODE))
