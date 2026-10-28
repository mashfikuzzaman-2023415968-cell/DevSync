"""Check for fastapi-api-security-08: wildcard origins + credentials reflects the caller's Origin."""

CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True)

@app.get("/me")
def me():
    return {"secret": 1}

c = TestClient(app)
evil = {"Origin": "https://evil.example"}
with_cookie = c.get("/me", headers={**evil, "Cookie": "session=abc"})
no_cookie = c.get("/me", headers=evil)
pre = c.options("/me", headers={**evil, "Access-Control-Request-Method": "GET"})
print(json.dumps({
    "status": with_cookie.status_code,
    "cookie_acao": with_cookie.headers.get("access-control-allow-origin"),
    "cookie_acac": with_cookie.headers.get("access-control-allow-credentials"),
    "nocookie_acao": no_cookie.headers.get("access-control-allow-origin"),
    "pre_acao": pre.headers.get("access-control-allow-origin"),
    "pre_acac": pre.headers.get("access-control-allow-credentials"),
}))
"""


def check(ctx, q):
    import json

    got = json.loads(ctx.python(CODE))
    assert got["status"] == 200, got  # not blocked server-side (distractor A)
    assert got["cookie_acao"] == "https://evil.example", (
        got
    )  # echoed, not "*" (B), not app origin (C)
    assert got["cookie_acac"] == "true", got
    assert got["pre_acao"] == "https://evil.example" and got["pre_acac"] == "true", got
    opts = q["options"]
    assert opts[q["correct_index"]].startswith("The API echoes evil.example"), opts
