"""Check for fastapi-async-performance-07: async background task blocks the loop; def task does not."""

CODE = r'''
import warnings
warnings.filterwarnings("ignore")
import asyncio, time, json
import httpx
from fastapi import FastAPI, BackgroundTasks

def build(variant):
    app = FastAPI()

    async def build_async():
        time.sleep(1)

    def build_sync():
        time.sleep(1)

    task = build_async if variant in ("async_task", "def_route") else build_sync

    if variant == "def_route":
        @app.post("/export")
        def export(bg: BackgroundTasks):
            bg.add_task(task)
            return {"queued": True}
    else:
        @app.post("/export")
        async def export(bg: BackgroundTasks):
            bg.add_task(task)
            return {"queued": True}

    @app.get("/ping")
    async def ping():
        return {"ok": True}
    return app

async def measure(variant):
    app = build(variant)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        t = time.perf_counter()
        post = asyncio.create_task(c.post("/export"))
        await asyncio.sleep(0.2)
        r = await c.get("/ping")
        ping_done = time.perf_counter() - t  # measured from the start of the export request
        await post
        return round(ping_done, 1)

print(json.dumps({v: asyncio.run(measure(v)) for v in ["async_task", "def_route", "sync_task"]}))
'''


def check(ctx, q):
    import json

    got = json.loads(ctx.python(CODE))
    assert got["async_task"] >= 0.9, got  # the marked cause: the loop is blocked, ping waits
    assert got["sync_task"] <= 0.4, got  # marked fix: plain def task, ping stays fast
    assert got["def_route"] >= 0.9, got  # distractor C: def route does not help
    opts = q["options"]
    assert opts[q["correct_index"]].startswith("build_report is async def"), opts
    assert opts[2].startswith("Making export a plain def"), opts
