"""Check for fastapi-databases-orm-03: POST without commit, then GET, against a real SQLite file."""

CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import json, os, tempfile
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

engine = create_engine("sqlite:///" + os.path.join(tempfile.mkdtemp(), "t.db"))
SessionLocal = sessionmaker(engine)

class Base(DeclarativeBase):
    pass

class Item(Base):
    __tablename__ = "items"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]

Base.metadata.create_all(engine)
app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/items")
def create_item(name: str, db: Session = Depends(get_db)):
    db.add(Item(name=name))
    return {"ok": True}

@app.get("/items")
def list_items(db: Session = Depends(get_db)):
    return [i.name for i in db.scalars(select(Item))]

c = TestClient(app)
assert c.post("/items?name=pen").status_code == 200
r = c.get("/items")
print(json.dumps(r.json()) if r.status_code == 200 else f"Status {r.status_code}")
"""

FIXED = CODE.replace(
    "    db.add(Item(name=name))\n", "    db.add(Item(name=name))\n    db.commit()\n"
)


def check(ctx, q):
    ctx.expect_only(q, ctx.python(CODE))
    assert ctx.python(FIXED).strip() == '["pen"]'  # with a commit the row is there
