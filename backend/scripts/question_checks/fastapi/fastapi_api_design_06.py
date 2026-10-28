"""Check for fastapi-api-design-06: send each candidate source of the value and see which one works."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import json
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/ping")
def ping(x_token: str = Header()):
    return {"token": x_token}

c = TestClient(app)
print(json.dumps({
    "hyphen": c.get("/ping", headers={"X-Token": "v"}).status_code,
    "underscore": c.get("/ping", headers={"x_token": "v"}).status_code,
    "authorization": c.get("/ping", headers={"Authorization": "v"}).status_code,
    "query": c.get("/ping?x_token=v").status_code,
}))
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    import json

    got = json.loads(ctx.python(CODE))
    assert got == {"hyphen": 200, "underscore": 422, "authorization": 422, "query": 422}, got
    opts = q["options"]
    assert opts[q["correct_index"]].startswith("X-Token"), (
        "marked option must be the hyphenated header"
    )
    texts = {
        o.split(",")[0].split(":")[0].split(" ")[0]
        for i, o in enumerate(opts)
        if i != q["correct_index"]
    }
    assert texts == {"x_token", "Authorization", "None"}, texts
