"""Check for fastapi-async-performance-02: two concurrent requests, time.sleep vs asyncio.sleep."""

CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import asyncio, time
import httpx
from fastapi import FastAPI

app = FastAPI()

@app.get("/slow")
async def slow():
    time.sleep(1)
    return {"ok": True}

@app.get("/ok")
async def ok():
    await asyncio.sleep(1)
    return {"ok": True}

async def both(path):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        t = time.perf_counter()
        rs = await asyncio.gather(c.get(path), c.get(path))
        assert all(r.status_code == 200 for r in rs)
        return time.perf_counter() - t

print(round(asyncio.run(both("/slow")), 2), round(asyncio.run(both("/ok")), 2))
"""


def check(ctx, q):
    blocking, cooperative = (float(x) for x in ctx.python(CODE).split())
    assert 1.9 <= blocking <= 2.5, blocking
    assert 0.9 <= cooperative <= 1.4, cooperative
    label = "About 2 seconds"
    ctx.expect_only(q, label)
