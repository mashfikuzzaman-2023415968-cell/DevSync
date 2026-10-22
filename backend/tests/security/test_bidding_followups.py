"""Phase 5 follow-ups over HTTP (DECISIONS D54): bidding closes by time, bids reference only
the bidder's own portfolio, the client's bids view explains every verdict, the too-few-bids
actions (preview, apply, rules, notifications), extend/cancel, search pagination for every sort
and skill-name search, recommendations (§9.16), and sign-in with reserved-domain demo emails.

Eligibility needs controllable reputations: developers get a skill through the API and an
experienced reputation snapshot written with the migrator role (snapshots are SYSTEM-only to
write through the app, §14.15).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, text

from tests.helpers import Api, SeededUser

pytestmark = [pytest.mark.security, pytest.mark.api]


# --------------------------------------------------------------------------- helpers


def _sql(url: str, stmt: str, **params: Any) -> list[Any]:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            result = conn.execute(text(stmt), params)
            return list(result) if result.returns_rows else []
    finally:
        engine.dispose()


def _skill(api: Api, index: int = 0) -> dict[str, Any]:
    skills = api.get("/api/v1/skills").json()
    return skills[index]


def _skill_id(skill: dict[str, Any]) -> str:
    return str(skill.get("skill_id") or skill["id"])


def _publish(
    api: Api,
    *,
    title: str = "Online ordering system",
    budget: int = 12_000_000,
    deadline_days: int = 30,
    count: int = 2,
    skill_index: int = 0,
) -> tuple[str, str]:
    """As the signed-in client: create, plan, verify payment, publish → (project_id, slot_id)."""
    sid = _skill_id(_skill(api, skill_index))
    pid = api.post(
        "/api/v1/projects",
        json={
            "title": title,
            "summary": "Order and track restaurant orders.",
            "budget_paisa": budget,
            "deadline_days": deadline_days,
            "team_size": count,
        },
    ).json()["id"]
    slots = api.put(
        f"/api/v1/projects/{pid}/slots", json={"slots": [{"skill_id": sid, "count": count}]}
    ).json()
    api.put(
        f"/api/v1/projects/{pid}/milestones",
        json={
            "milestones": [
                {"name": "Design", "duration_days": 5, "share_bp": 6000, "skill_ids": [sid]},
                {"name": "Build", "duration_days": 10, "share_bp": 4000, "skill_ids": [sid]},
            ]
        },
    )
    assert api.post("/api/v1/me/payment-method/verify").status_code == 204
    published = api.post(f"/api/v1/projects/{pid}/publish", json={})
    assert published.status_code == 200, published.text
    return pid, slots[0]["id"]


def _developer(
    api: Api, url: str, *, p: float = 0.80, c: float = 0.75, skill_index: int = 0
) -> SeededUser:
    """Sign in a developer who lists the skill and has an experienced reputation."""
    dev = api.sign_in_as("DEVELOPER")
    sid = _skill_id(_skill(api, skill_index))
    r = api.put("/api/v1/me/skills", json={"skills": [{"skill_id": sid, "self_level": 4}]})
    assert r.status_code == 200, r.text
    _sql(
        url,
        "INSERT INTO reputation_snapshots (id, developer_id, omega, x, xm, beta, mu, t, c, p, "
        "completed_projects, distinct_clients) VALUES (:id, :dev, 0.6, 0.7, 0.66, 0.8, 0.7, 0.8, "
        ":c, :p, 6, 4)",
        id=str(uuid.uuid4()),
        dev=dev.user_id,
        c=c,
        p=p,
    )
    return dev


def _bid(api: Api, pid: str, slot_id: str, **over: Any) -> Any:
    body = {"slot_id": slot_id, "price_paisa": 1_800_000, "days_needed": 20, **over}
    return api.post(f"/api/v1/projects/{pid}/bids", json=body)


def _close_bidding(url: str, pid: str) -> None:
    _sql(
        url,
        "UPDATE projects SET bidding_deadline = now() - interval '1 hour' WHERE id = :pid",
        pid=pid,
    )


def _notifications(url: str, user_id: str, kind: str) -> int:
    rows = _sql(
        url,
        "SELECT count(*) FROM notifications WHERE user_id = :uid AND type = :kind",
        uid=user_id,
        kind=kind,
    )
    return int(rows[0][0])


# --------------------------------------------------------------------------- bidding closes by time


def test_bids_are_refused_after_the_bidding_deadline(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    dev = _developer(api, migration_url)
    bid_id = _bid(api, pid, slot_id).json()["id"]

    _close_bidding(migration_url, pid)  # the job hasn't run: status is still BIDDING
    for r in (
        _bid(api, pid, slot_id),
        api.patch(f"/api/v1/bids/{bid_id}", json={"price_paisa": 1_700_000}),
        api.delete(f"/api/v1/bids/{bid_id}"),
        api.post(
            f"/api/v1/projects/{pid}/bids/eligibility",
            json={"slot_id": slot_id, "price_paisa": 1_800_000, "days_needed": 20},
        ),
    ):
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "INVALID_STATE"
    # The bid is untouched and the project disappears from search; its page says it's closed.
    mine = [b for b in api.get("/api/v1/me/bids").json() if b["id"] == bid_id]
    assert mine[0]["status"] == "ACTIVE"
    assert mine[0]["price_paisa"] == 1_800_000
    found = api.get("/api/v1/projects/search", params={"limit": 100}).json()["items"]
    assert pid not in {p["id"] for p in found}
    detail = api.get(f"/api/v1/public/projects/{pid}").json()
    assert detail["open_for_bids"] is False
    assert dev.user_id


def test_open_projects_say_they_take_bids(api: Api) -> None:
    api.sign_in_as("CLIENT")
    pid, _slot = _publish(api)
    assert api.get(f"/api/v1/public/projects/{pid}").json()["open_for_bids"] is True


def test_withdraw_then_bid_again(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)
    _developer(api, migration_url)
    first = _bid(api, pid, slot_id).json()["id"]
    assert api.delete(f"/api/v1/bids/{first}").status_code == 204
    second = _bid(api, pid, slot_id, price_paisa=1_600_000)
    assert second.status_code == 201, second.text
    statuses = {b["id"]: b["status"] for b in api.get("/api/v1/me/bids").json()}
    assert statuses[first] == "WITHDRAWN"
    assert statuses[second.json()["id"]] == "ACTIVE"


# --------------------------------------------------------------------------- portfolio ownership


def test_bids_attach_only_the_bidders_own_portfolio_items(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api)

    other = _developer(api, migration_url)
    foreign = api.post("/api/v1/me/portfolio", json={"title": "Someone else's work"}).json()["id"]
    assert other.user_id

    _developer(api, migration_url)
    mine = api.post("/api/v1/me/portfolio", json={"title": "My ordering app"}).json()["id"]

    for items, detail in (
        ([foreign], "not one of your portfolio items"),
        ([str(uuid.uuid4())], "not one of your portfolio items"),
        ([mine, mine], "duplicate item"),
    ):
        r = _bid(api, pid, slot_id, portfolio_item_ids=items)
        assert r.status_code == 422, r.text
        assert r.json()["error"]["fields"] == {"portfolio_item_ids": detail}

    created = _bid(api, pid, slot_id, portfolio_item_ids=[mine])
    assert created.status_code == 201, created.text
    bid_id = created.json()["id"]
    edit = api.patch(f"/api/v1/bids/{bid_id}", json={"portfolio_item_ids": [foreign]})
    assert edit.status_code == 422
    assert api.patch(f"/api/v1/bids/{bid_id}", json={"portfolio_item_ids": []}).status_code == 200


# --------------------------------------------------------------------------- explained client view


def test_client_view_explains_each_verdict(api: Api, migration_url: str) -> None:
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api, budget=12_000_000)
    _developer(api, migration_url)
    item = api.post("/api/v1/me/portfolio", json={"title": "Kitchen orders"}).json()["id"]
    _bid(
        api,
        pid,
        slot_id,
        proposal="React front end with tests.",
        portfolio_item_ids=[item],
        hours_per_week_committed=15,
    )
    _developer(api, migration_url, p=0.80)
    _bid(api, pid, slot_id, days_needed=31)  # too slow for the 30-day deadline

    api.login(client)
    body = api.get(f"/api/v1/projects/{pid}/bids").json()
    rows = sorted(body["bids"], key=lambda b: b["days_needed"])
    fast, slow = rows
    assert fast["eligible"] is True
    assert fast["shortlisted"] is True
    assert fast["hours_per_week"] == 15
    assert fast["teamwork"] == pytest.approx(0.66)
    assert fast["proposal"] == "React front end with tests."
    assert fast["portfolio"] == [{"id": item, "title": "Kitchen orders"}]
    assert all(c["ok"] for c in fast["checks"])
    # One slot of two is short, so relaxation ran all three steps: the project's own minimum
    # stays 45 and every trace shows the minimum actually used (30).
    perf = next(c for c in fast["checks"] if c["name"] == "performance")
    assert body["thresholds"]["used_p0"] == pytest.approx(0.30)
    assert perf["required"] == pytest.approx(body["thresholds"]["used_p0"])
    assert perf["actual"] == pytest.approx(0.80)
    assert slow["eligible"] is False
    assert slow["reasons"] == ["TOO_SLOW"]
    days = next(c for c in slow["checks"] if c["name"] == "days")
    assert days == {
        "name": "days",
        "ok": False,
        "detail": "31 days (deadline 30 days)",
        "required": 30,
        "actual": 31,
    }
    # Thresholds, team cost, bidding window and the "as of" time.
    assert body["thresholds"]["p0"] == pytest.approx(0.45)
    assert body["thresholds"]["floor_p0"] == pytest.approx(0.30)
    assert body["team_cost"] == {
        "total_paisa": 1_800_000,
        "budget_after_fee_paisa": body["team_cost"]["budget_after_fee_paisa"],
        "complete": False,
    }
    assert body["bidding"]["closed"] is False
    assert body["bidding"]["max_extensions"] == 2
    assert datetime.fromisoformat(body["evaluated_at"]) <= datetime.now(UTC) + timedelta(minutes=1)


def test_preview_never_ranks_against_other_bids(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api, count=2)
    _developer(api, migration_url)
    r = api.post(
        f"/api/v1/projects/{pid}/bids/eligibility",
        json={"slot_id": slot_id, "price_paisa": 1_800_000, "days_needed": 20},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"eligible", "reason", "message", "checks"}
    assert body["reason"] != "NOT_SHORTLISTED"
    assert {c["name"] for c in body["checks"]} <= {
        "account_active",
        "has_slot_skill",
        "no_conflict",
        "available",
        "skill_evidence",
        "performance",
        "competency",
        "days",
        "price",
    }


# --------------------------------------------------------------------------- too-few-bids actions


def _short_project(api: Api, url: str) -> tuple[SeededUser, str, str, list[SeededUser]]:
    """A 2-place slot with one eligible bid, one too-weak bid (P 0.35) and one over budget."""
    client = api.sign_in_as("CLIENT")
    pid, slot_id = _publish(api, budget=6_000_000, count=2)
    devs = [_developer(api, url)]
    assert _bid(api, pid, slot_id).status_code == 201
    devs.append(_developer(api, url, p=0.25))
    assert _bid(api, pid, slot_id).status_code == 201
    devs.append(_developer(api, url))
    assert _bid(api, pid, slot_id, price_paisa=6_500_000).status_code == 201
    api.login(client)
    return client, pid, slot_id, devs


def test_preview_shows_the_effect_without_saving(api: Api, migration_url: str) -> None:
    _client, pid, _slot, _devs = _short_project(api, migration_url)
    before = api.get(f"/api/v1/projects/{pid}/bids").json()
    assert before["too_few"] is True

    r = api.post(f"/api/v1/projects/{pid}/bidding-terms/preview", json={"budget_paisa": 8_000_000})
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["before"]["too_few"] is True
    assert preview["after"]["too_few"] is False
    assert preview["newly_eligible"] == 1
    assert preview["after"]["eligible"] == preview["before"]["eligible"] + 1
    assert "1 more bid would be eligible" in preview["message"]
    # Nothing was saved.
    after = api.get(f"/api/v1/projects/{pid}/bids").json()
    assert after["budget_paisa"] == before["budget_paisa"]
    assert after["too_few"] is True


def test_raising_the_budget_applies_audits_and_notifies(api: Api, migration_url: str) -> None:
    _client, pid, _slot, devs = _short_project(api, migration_url)
    version = api.get(f"/api/v1/projects/{pid}").json()["version"]
    stale = api.patch(
        f"/api/v1/projects/{pid}/bidding-terms",
        json={"budget_paisa": 8_000_000},
        headers={"If-Match": str(version - 1)},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"

    r = api.patch(
        f"/api/v1/projects/{pid}/bidding-terms",
        json={"budget_paisa": 8_000_000},
        headers={"If-Match": str(version)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["budget_paisa"] == 8_000_000
    assert r.json()["too_few"] is False
    assert api.get(f"/api/v1/projects/{pid}").json()["version"] == version + 1
    for dev in devs:
        assert _notifications(migration_url, dev.user_id, "PROJECT_TERMS_CHANGED") == 1
    audits = _sql(
        migration_url,
        "SELECT before->>'budget_paisa', after->>'budget_paisa' FROM audit_log "
        "WHERE action = 'project.terms_changed' AND entity_id = :pid",
        pid=pid,
    )
    assert [tuple(a) for a in audits] == [("6000000", "8000000")]


def test_lowering_standards_makes_weaker_bids_eligible(api: Api, migration_url: str) -> None:
    _client, pid, _slot, _devs = _short_project(api, migration_url)
    # P 0.25 is below even the relaxed 0.30, so the floor itself won't do; prove the floor holds.
    below = api.patch(f"/api/v1/projects/{pid}/bidding-terms", json={"min_performance": "0.20"})
    assert below.status_code == 422
    assert below.json()["error"]["fields"] == {"min_performance": "out of range"}
    above = api.patch(f"/api/v1/projects/{pid}/bidding-terms", json={"min_performance": "0.50"})
    assert above.status_code == 422

    r = api.patch(f"/api/v1/projects/{pid}/bidding-terms", json={"min_performance": "0.30"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["thresholds"]["p0"] == pytest.approx(0.30)
    # Relaxation continues from the client's own minimum (0.30 → 0.25 reaches the P 0.25 bid).
    assert body["thresholds"]["used_p0"] == pytest.approx(0.25)
    assert body["too_few"] is False


def test_reducing_the_team(api: Api, migration_url: str) -> None:
    _client, pid, slot_id, _devs = _short_project(api, migration_url)
    grow = api.patch(
        f"/api/v1/projects/{pid}/bidding-terms",
        json={"slot_counts": [{"slot_id": slot_id, "count": 3}]},
    )
    assert grow.status_code == 422
    tiny = api.patch(
        f"/api/v1/projects/{pid}/bidding-terms",
        json={"slot_counts": [{"slot_id": slot_id, "count": 1}]},
    )
    assert tiny.status_code == 422  # a team needs at least 2 people
    assert tiny.json()["error"]["fields"] == {"slot_counts": "team too small"}
    unknown = api.patch(
        f"/api/v1/projects/{pid}/bidding-terms",
        json={"slot_counts": [{"slot_id": str(uuid.uuid4()), "count": 1}]},
    )
    assert unknown.status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"budget_paisa": 1_000_000},  # lower than the current budget
        {"min_competency": "0.10"},
        {"min_performance": "0.333"},  # more than two decimals
        {"budget_paisa": 8_000_000, "status": "FORMING"},  # mass assignment
        {"slot_counts": []},
    ],
)
def test_invalid_terms_are_refused(api: Api, migration_url: str, body: dict[str, Any]) -> None:
    _client, pid, _slot, _devs = _short_project(api, migration_url)
    for path in ("bidding-terms/preview", "bidding-terms"):
        method = api.post if path.endswith("preview") else api.patch
        r = method(f"/api/v1/projects/{pid}/{path}", json=body)
        assert r.status_code == 422, (path, body, r.text)


def test_terms_belong_to_the_owning_client_while_bidding(api: Api, migration_url: str) -> None:
    _client, pid, _slot, _devs = _short_project(api, migration_url)
    change = {"budget_paisa": 8_000_000}
    api.sign_in_as("CLIENT")  # another client → 404 (existence hidden)
    assert api.patch(f"/api/v1/projects/{pid}/bidding-terms", json=change).status_code == 404
    api.sign_in_as("DEVELOPER")  # wrong role → 403
    assert api.patch(f"/api/v1/projects/{pid}/bidding-terms", json=change).status_code == 403
    assert api.post(f"/api/v1/projects/{pid}/bidding-terms/preview", json=change).status_code == 403


def test_terms_after_cancel_are_refused_and_bidders_are_told(api: Api, migration_url: str) -> None:
    _client, pid, _slot, devs = _short_project(api, migration_url)
    r = api.post(f"/api/v1/projects/{pid}/cancel", json={"reason": "Re-scoping the project."})
    assert r.status_code == 200, r.text
    for dev in devs:
        assert _notifications(migration_url, dev.user_id, "PROJECT_CANCELLED") == 1
    late = api.patch(f"/api/v1/projects/{pid}/bidding-terms", json={"budget_paisa": 8_000_000})
    assert late.status_code == 409


def test_fixing_a_closed_shortfall_moves_to_forming(api: Api, migration_url: str) -> None:
    _client, pid, _slot, _devs = _short_project(api, migration_url)
    _close_bidding(migration_url, pid)
    view = api.get(f"/api/v1/projects/{pid}/bids").json()
    assert view["bidding"]["closed"] is True
    assert view["too_few"] is True
    r = api.patch(f"/api/v1/projects/{pid}/bidding-terms", json={"budget_paisa": 8_000_000})
    assert r.status_code == 200, r.text
    assert api.get(f"/api/v1/projects/{pid}").json()["status"] == "FORMING"


def test_extending_after_the_deadline_counts_from_now(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, _slot = _publish(api)
    _close_bidding(migration_url, pid)
    r = api.post(f"/api/v1/projects/{pid}/extend-bidding")
    assert r.status_code == 200, r.text
    deadline = datetime.fromisoformat(r.json()["bidding_deadline"])
    assert deadline > datetime.now(UTC) + timedelta(days=2, hours=23)
    assert api.get(f"/api/v1/public/projects/{pid}").json()["open_for_bids"] is True


# ------------------------------------------------------------------ search and recommendations


def test_every_sort_pages_without_gaps_or_repeats(api: Api) -> None:
    api.sign_in_as("CLIENT")
    token = f"pager{uuid.uuid4().hex[:8]}"
    made = {
        _publish(api, title=f"{token} project {i}", budget=10_000_000 + i * 1_000_000,
                 deadline_days=20 + (i % 2))[0]
        for i in range(4)
    }  # fmt: skip
    api.sign_in_as("DEVELOPER")
    for sort in ("newest", "budget", "deadline"):
        seen: list[str] = []
        cursor: str | None = None
        pages = 0
        while True:
            params: dict[str, Any] = {"q": token, "sort": sort, "limit": 1}
            if cursor:
                params["cursor"] = cursor
            r = api.get("/api/v1/projects/search", params=params)
            assert r.status_code == 200, r.text
            seen += [p["id"] for p in r.json()["items"]]
            cursor = r.json()["next_cursor"]
            pages += 1
            if not cursor:
                break
        assert len(seen) == len(set(seen)) == 4, sort
        assert set(seen) == made
        assert pages == 4
    budgets = [
        p["budget_paisa"]
        for p in api.get("/api/v1/projects/search", params={"q": token, "sort": "budget"}).json()[
            "items"
        ]
    ]
    assert budgets == sorted(budgets, reverse=True)


def test_a_cursor_from_another_sort_is_refused(api: Api) -> None:
    api.sign_in_as("CLIENT")
    token = f"cursor{uuid.uuid4().hex[:8]}"
    for i in range(2):
        _publish(api, title=f"{token} project {i}")
    api.sign_in_as("DEVELOPER")
    cursor = api.get("/api/v1/projects/search", params={"q": token, "limit": 1}).json()[
        "next_cursor"
    ]
    r = api.get(
        "/api/v1/projects/search",
        params={"q": token, "limit": 1, "sort": "budget", "cursor": cursor},
    )
    assert r.status_code == 422
    assert r.json()["error"]["fields"] == {"cursor": "invalid"}


def test_text_search_matches_skill_names(api: Api) -> None:
    api.sign_in_as("CLIENT")
    token = f"skillq{uuid.uuid4().hex[:8]}"
    skill = _skill(api, 0)["name"]
    pid, _slot = _publish(api, title=f"{token} kitchen app", skill_index=0)
    api.sign_in_as("DEVELOPER")
    found = api.get("/api/v1/projects/search", params={"q": f"{token} {skill}"}).json()["items"]
    assert [p["id"] for p in found] == [pid]
    other = _skill(api, 3)["name"]
    if other.lower() != skill.lower():
        missing = api.get("/api/v1/projects/search", params={"q": f"{token} {other}"}).json()
        assert missing["items"] == []


def test_recommendations_fit_skills_pace_and_drop_after_bidding(
    api: Api, migration_url: str
) -> None:
    api.sign_in_as("CLIENT")
    first, slot_id = _publish(api, deadline_days=30)
    short, _ = _publish(api, deadline_days=30)
    long, _ = _publish(api, deadline_days=45)
    _developer(api, migration_url)
    recs = {r["project"]["id"]: r for r in api.get("/api/v1/projects/recommended").json()}
    # No past bids yet: any deadline fits.
    assert {first, short, long} <= set(recs)
    assert recs[first]["matched_skills"]
    assert recs[first]["typical_days"] is None

    # Bidding 40 days forgets the cached list. The project bid on is no longer recommended, and
    # the developer's usual pace for the skill is now 40 days: the other 30-day project drops out
    # and the 45-day one stays, showing that pace.
    assert _bid(api, first, slot_id, days_needed=40).status_code == 201
    recs = {r["project"]["id"]: r for r in api.get("/api/v1/projects/recommended").json()}
    assert first not in recs
    assert short not in recs
    assert long in recs
    assert recs[long]["typical_days"] == 40


def test_recommendations_need_free_hours(api: Api, migration_url: str) -> None:
    api.sign_in_as("CLIENT")
    pid, _slot = _publish(api)
    dev = _developer(api, migration_url)
    # A confirmed reservation filling the developer's week over the same period.
    _sql(
        migration_url,
        "INSERT INTO availability_reservations (id, developer_id, project_id, hours_per_week, "
        "from_date, to_date, status) VALUES (:id, :dev, :pid, 40, current_date - 1, "
        "current_date + 400, 'CONFIRMED')",
        id=str(uuid.uuid4()),
        dev=dev.user_id,
        pid=pid,
    )
    api.post("/api/v1/auth/logout")
    api.login(dev)
    assert pid not in {r["project"]["id"] for r in api.get("/api/v1/projects/recommended").json()}


# ---------------------------------------------------------------------- reserved-domain sign-in


def test_reserved_domain_accounts_can_sign_in(api: Api, migration_url: str) -> None:
    """The seeded demo accounts use `@devsync.local` (spec §18.4); sign-in must accept it."""
    user = api.seed("CLIENT")
    local = f"demo-{uuid.uuid4().hex[:8]}@DevSync.local"
    _sql(migration_url, "UPDATE users SET email = :e WHERE id = :uid", e=local, uid=user.user_id)
    r = api.post(
        "/api/v1/auth/login",
        json={"email": local, "password": user.password, "captcha": "test-bypass"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "SIGNED_IN"
    forgot = api.post(
        "/api/v1/auth/password/forgot", json={"email": local, "captcha": "test-bypass"}
    )
    assert forgot.status_code == 202


@pytest.mark.parametrize("email", ["not-an-email", "a b@c.d", "@devsync.local", "x@", "x\x00@y.z"])
def test_sign_in_still_rejects_malformed_emails(api: Api, email: str) -> None:
    r = api.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "whatever 123", "captcha": "test-bypass"},
    )
    assert r.status_code == 422


def test_registration_still_refuses_reserved_domains(api: Api) -> None:
    r = api.post(
        "/api/v1/auth/register",
        json={
            "display_name": "Local Domain",
            "email": f"x{uuid.uuid4().hex[:6]}@devsync.local",
            "phone": "+8801712345678",
            "password": "a long passphrase 42!",
            "role": "CLIENT",
            "accept_terms": True,
            "captcha": "test-bypass",
        },
    )
    assert r.status_code == 422
    assert "email" in r.json()["error"]["fields"]
