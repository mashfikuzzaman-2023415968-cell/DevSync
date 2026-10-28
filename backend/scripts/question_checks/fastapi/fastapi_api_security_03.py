"""Check for fastapi-api-security-03: the injection payload against a real SQLite table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import json
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE users (name TEXT)"))
    conn.execute(text("INSERT INTO users VALUES ('ann'), ('bob')"))
SessionLocal = sessionmaker(engine)
app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/users")
def find_user(name: str, db: Session = Depends(get_db)):
    query = text(f"SELECT name FROM users WHERE name = '{name}'")
    return [row[0] for row in db.execute(query)]

@app.get("/safe")
def find_safe(name: str, db: Session = Depends(get_db)):
    return [row[0] for row in db.execute(text("SELECT name FROM users WHERE name = :n"), {"n": name})]

c = TestClient(app)
payload = "x' OR '1'='1"
r = c.get("/users", params={"name": payload})
print(json.dumps(r.json()) if r.status_code == 200 else f"Status {r.status_code}")
print(json.dumps(c.get("/safe", params={"name": payload}).json()))
print(json.dumps(c.get("/users", params={"name": "ann"}).json()))
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    injected, safe, normal = ctx.python(CODE).strip().splitlines()
    ctx.expect_only(q, injected)
    assert safe == "[]" and normal == '["ann"]'
