"""Check for fastapi-async-performance-05: gather() re-raises but does not cancel siblings."""

CODE = r'''
import asyncio

async def job(name, delay, fail=False):
    await asyncio.sleep(delay)
    if fail:
        raise ValueError(name)
    print(name, "done")

async def main():
    try:
        await asyncio.gather(job("a", 0.1, True), job("b", 0.3))
    except ValueError as e:
        print("caught", e)
    await asyncio.sleep(0.5)

asyncio.run(main())
'''


def check(ctx, q):
    lines = ctx.python(CODE).strip().splitlines()
    assert lines == ["caught a", "b done"], lines
    ctx.expect_only(q, ", then ".join(lines))
