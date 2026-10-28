"""Check for fastapi-async-performance-06: 50 sync-def sleeps use 40 threads; 50 async-def sleeps serialise."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx


CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import asyncio, time
import httpx
from fastapi import FastAPI

app = FastAPI()

@app.get("/a")
def a():
    time.sleep(0.1)
    return {"ok": True}

@app.get("/b")
async def b():
    time.sleep(0.1)
    return {"ok": True}

async def run(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        t = time.perf_counter()
        rs = await asyncio.gather(*(c.get(path) for _ in range(50)))
        assert all(r.status_code == 200 for r in rs)
        return time.perf_counter() - t

print(round(asyncio.run(run("/a")), 1), round(asyncio.run(run("/b")), 1))
"""


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    a, b = (float(x) for x in ctx.python(CODE).split())
    assert 0.15 <= a <= 0.35, a
    assert 4.9 <= b <= 5.8, b
    ctx.expect_only(q, "About 0.2 s for /a and about 5 s for /b")
