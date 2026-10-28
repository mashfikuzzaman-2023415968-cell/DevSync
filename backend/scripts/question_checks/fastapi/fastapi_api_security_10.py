"""Check for fastapi-api-security-10: which next values the startswith('/') check lets through."""

CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import json
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/login/done")
def done(next: str = "/"):
    if not next.startswith("/"):
        next = "/"
    return RedirectResponse(next)

c = TestClient(app, follow_redirects=False)
out = {}
for v in ["https://evil.example/x", "evil.example.net/x", "//evil.example/x", "javascript:alert(1)"]:
    out[v] = c.get("/login/done", params={"next": v}).headers["location"]
print(json.dumps(out))
"""


def check(ctx, q):
    import json

    got = json.loads(ctx.python(CODE))
    leaking = [v for v, loc in got.items() if loc == v]
    assert leaking == ["//evil.example/x"], got  # only the protocol-relative value is kept
    ctx.expect_only(q, leaking[0])
