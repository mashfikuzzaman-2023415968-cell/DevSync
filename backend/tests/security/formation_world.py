"""Shared test data for the formation and team API tests (not a test module): a client's FORMING
project with one slot for two developers and five bidders, one a qualified newcomer."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Coroutine
from typing import Any

from sqlalchemy import create_engine, text

from app.core.redis import forget_clients
from tests.helpers import Api, SeededUser

BASE = "/api/v1"
UNKNOWN = "00000000-0000-4000-8000-000000000000"


def _sql(url: str, stmt: str, **params: Any) -> list[Any]:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            result = conn.execute(text(stmt), params)
            return list(result) if result.returns_rows else []
    finally:
        engine.dispose()


def _job[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a job here (the test stack has no worker), then drop the Redis clients it cached:
    they belong to its event loop, which has ended."""
    try:
        return asyncio.run(coro)
    finally:
        forget_clients()


def _code(r: Any) -> str:
    return str(r.json()["error"]["code"])


def _skill_id(api: Api) -> str:
    skill = api.get(f"{BASE}/skills").json()[0]
    return str(skill.get("skill_id") or skill["id"])


def _publish(api: Api, *, count: int = 2) -> tuple[str, str]:
    sid = _skill_id(api)
    pid = api.post(
        f"{BASE}/projects",
        json={
            "title": "Online ordering system",
            "summary": "Order and track restaurant orders.",
            "budget_paisa": 12_000_000,
            "deadline_days": 30,
            "team_size": count,
        },
    ).json()["id"]
    slots = api.put(
        f"{BASE}/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": count}]}
    ).json()
    saved = api.put(
        f"{BASE}/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
            ]
        },
    )
    ids = {m["name"]: m["id"] for m in saved.json()}
    r = api.put(
        f"{BASE}/projects/{pid}/dependencies",
        json={"dependencies": [{"predecessor_id": ids["Design"], "successor_id": ids["Build"]}]},
    )
    assert r.status_code == 200, r.text
    assert api.post(f"{BASE}/me/payment-method/verify").status_code == 204
    assert api.post(f"{BASE}/projects/{pid}/publish", json={}).status_code == 200
    return pid, slots[0]["id"]


def _bidder(
    api: Api,
    url: str,
    pid: str,
    slot: str,
    *,
    price: int,
    days: int,
    p: float,
    c: float,
    newcomer: bool = False,
) -> tuple[SeededUser, str]:
    dev = api.sign_in_as("DEVELOPER")
    r = api.put(
        f"{BASE}/me/skills", json={"skills": [{"skill_id": _skill_id(api), "self_level": 4}]}
    )
    assert r.status_code == 200, r.text
    if newcomer:
        assert (
            api.post(
                f"{BASE}/__test__/developers/{dev.user_id}/skill-evidence",
                json={"skill": api.get(f"{BASE}/skills").json()[0]["name"], "score": "0.900"},
            ).status_code
            == 204
        )
        api.qualify_for_slot(dev, pid, slot, api.get(f"{BASE}/skills").json()[0]["name"])
    else:
        _sql(
            url,
            "INSERT INTO reputation_snapshots (id, developer_id, omega, x, xm, beta, mu, t, "
            "c, p, completed_projects, distinct_clients) VALUES (:id, :dev, 0.6, 0.7, 0.66, 0.8, "
            "0.7, 0.8, :c, :p, 6, 4)",
            id=str(uuid.uuid4()),
            dev=dev.user_id,
            c=c,
            p=p,
        )
    r = api.post(
        f"{BASE}/projects/{pid}/bids",
        json={"slot_id": slot, "price_paisa": price, "days_needed": days},
    )
    assert r.status_code == 201, r.text
    return dev, r.json()["id"]


def _forming(url: str, pid: str) -> None:
    _sql(
        url,
        "UPDATE projects SET bidding_deadline = now() - interval '1 hour', "
        "status = 'FORMING' WHERE id = :pid",
        pid=pid,
    )


def make_world(api: Api, api2: Api, migration_url: str) -> dict[str, Any]:
    client = api.sign_in_as("CLIENT")
    pid, slot = _publish(api)
    specs = [
        (3_000_000, 20, 0.85, 0.80),
        (2_400_000, 18, 0.70, 0.65),
        (4_200_000, 25, 0.90, 0.88),
        (2_000_000, 28, 0.60, 0.55),
    ]
    bidders = [
        _bidder(api2, migration_url, pid, slot, price=pr, days=d, p=p, c=c) for pr, d, p, c in specs
    ]
    bidders.append(
        _bidder(api2, migration_url, pid, slot, price=1_900_000, days=22, p=0, c=0, newcomer=True)
    )
    _forming(migration_url, pid)
    return {"client": client, "pid": pid, "slot": slot, "bidders": bidders}
