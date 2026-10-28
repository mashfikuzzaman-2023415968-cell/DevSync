"""Role assessment in the database (role assessment spec §4, §5.3, §6, §7.4, §10, §15–§17.3).

Everything runs against the real SECURITY DEFINER functions of migration 0011, as the runtime
roles (`devsync_app` for developers, clients, admins and guests; `devsync_worker` for SYSTEM).
Fixtures (competencies, approved questions, blueprints, scored-by-hand attempts) are inserted as
the migrator with unique codes per run, and removed again when the module finishes. The
competencies are created inactive so the blueprint builder and the real bank never see them.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from app.core.config import Environment
from app.core.security import hash_password
from app.db.context import DbContext
from app.db.session import open_session
from app.models import User, UserRole, UserStatus
from app.models.projects import Project, ProjectSlot, ProjectStatus
from tests.helpers import stack_available, unique_email, unique_phone

pytestmark = pytest.mark.integration

T0 = datetime(2026, 10, 28, 10, 0, 0, tzinfo=UTC)
LIMIT = 900  # seconds
GRACE = 5  # seconds after the deadline (spec §6.3)
RULE = {"overall_bp": 6000, "floor_bp": 4000, "heavy_weight_bp": 2000}
VECTORS = Path(__file__).resolve().parents[1] / "fixtures" / "assessment_scoring_vectors.json"

CHECK_VIOLATION = "23514"
NO_DATA = "P0002"
INSUFFICIENT = "42501"
UNIQUE_VIOLATION = "23505"


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


# ------------------------------------------------------------------------------ migrator side


@dataclass
class World:
    """A blueprint over `len(weights)` competencies with 1 easy + 1 medium + 1 hard question each,
    plus spare questions in the states the start function must refuse."""

    skill_id: uuid.UUID
    blueprint_id: uuid.UUID
    comps: list[uuid.UUID]
    ids: list[uuid.UUID]  # the valid selection, competency by competency, easy → hard
    correct: dict[uuid.UUID, int]
    spare_easy: uuid.UUID  # approved, comp 0, easy
    spare_medium: uuid.UUID  # approved, comp 0, medium
    draft_easy: uuid.UUID  # DRAFT, comp 0, easy
    retired_easy: uuid.UUID  # RETIRED, comp 0, easy
    outside_easy: uuid.UUID  # approved, a competency that is not in the blueprint
    fingerprint: str


class Mig:
    """Direct access as `devsync_migrator` (sync) to build and inspect fixtures."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.blueprints: list[uuid.UUID] = []
        self.fingerprints: list[str] = []
        self.questions: list[uuid.UUID] = []
        self.comps: list[uuid.UUID] = []

    def run(self, sql: str, **params: Any) -> list[dict[str, Any]]:
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params)
            return [dict(r) for r in result.mappings().all()] if result.returns_rows else []

    def scalar(self, sql: str, **params: Any) -> Any:
        rows = self.run(sql, **params)
        return next(iter(rows[0].values())) if rows else None

    def any_skill(self) -> uuid.UUID:
        return uuid.UUID(str(self.scalar("SELECT id FROM skills ORDER BY name LIMIT 1")))

    def competency(self, skill_id: uuid.UUID, tag: str) -> uuid.UUID:
        cid = self.scalar(
            "INSERT INTO competencies (skill_id, code, name, description, is_core, keywords, "
            "position, active) VALUES (:s, :c, :n, '', false, ARRAY['rtkw'], 0, false) "
            "RETURNING id",
            s=skill_id,
            c=f"rt{tag}",
            n=f"RT competency {tag}",
        )
        self.comps.append(cid)
        return uuid.UUID(str(cid))

    def question(
        self,
        skill_id: uuid.UUID,
        comp: uuid.UUID,
        difficulty: int,
        *,
        status: str = "APPROVED",
        review: str = "SELF_VERIFIED",
        correct: int = 1,
    ) -> uuid.UUID:
        slug = f"rt-{uuid.uuid4().hex}"
        qid = self.scalar(
            "INSERT INTO question_bank (skill_id, text, options, correct_index, difficulty, "
            "active, slug, competency_id, status, review_level, reviewed_at) "
            "VALUES (:s, :t, CAST(:o AS jsonb), :c, :d, false, :slug, :comp, "
            "CAST(:st AS question_status), CAST(:rv AS review_level), now()) RETURNING id",
            s=skill_id,
            t=f"Role assessment test question {slug}",
            o=json.dumps(["opt a", "opt b", "opt c", "opt d"]),
            c=correct,
            d=difficulty,
            slug=slug,
            comp=comp,
            st="APPROVED" if status == "RETIRED" else status,
            rv=review,
        )
        qid = uuid.UUID(str(qid))
        if status == "RETIRED":
            self.run("UPDATE question_bank SET status = 'RETIRED' WHERE id = :i", i=qid)
        self.questions.append(qid)
        return qid

    def blueprint(
        self,
        skill_id: uuid.UUID,
        comps: list[dict[str, Any]],
        *,
        count: int,
        time_limit: int = LIMIT,
        rule: dict[str, int] | None = None,
        available: bool = True,
    ) -> tuple[uuid.UUID, str]:
        fingerprint = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
        bid = self.scalar(
            "INSERT INTO assessment_blueprints (algo_version, fingerprint, primary_skill_id, "
            "label, competencies, question_count, time_limit_seconds, difficulty_mix, "
            "pass_rule, status, unavailable_reason) VALUES (1, :f, :s, 'RT role', "
            "CAST(:c AS jsonb), :n, :t, CAST(:m AS jsonb), CAST(:r AS jsonb), "
            "CAST(:st AS blueprint_status), :u) RETURNING id",
            f=fingerprint,
            s=skill_id,
            c=json.dumps(comps),
            n=count,
            t=time_limit,
            m=json.dumps({"easy": 1, "medium": 1, "hard": 1}),
            r=json.dumps(rule or RULE),
            st="AVAILABLE" if available else "UNAVAILABLE",
            u=None if available else "test",
        )
        bid = uuid.UUID(str(bid))
        self.blueprints.append(bid)
        self.fingerprints.append(fingerprint)
        return bid, fingerprint

    def world(
        self,
        weights: tuple[int, ...] = (5000, 5000),
        *,
        time_limit: int = LIMIT,
        available: bool = True,
    ) -> World:
        skill = self.any_skill()
        tag = uuid.uuid4().hex[:12]
        comps = [self.competency(skill, f"{tag}{i}") for i in range(len(weights))]
        outside = self.competency(skill, f"{tag}x")
        correct: dict[uuid.UUID, int] = {}
        ids: list[uuid.UUID] = []
        entries: list[dict[str, Any]] = []
        for i, (cid, weight) in enumerate(zip(comps, weights, strict=True)):
            for difficulty in (1, 2, 3):
                key = (i + difficulty) % 4
                q = self.question(skill, cid, difficulty, correct=key)
                correct[q] = key
                ids.append(q)
            entries.append(
                {
                    "competency_id": str(cid),
                    "code": f"rt{tag}{i}",
                    "name": f"RT competency {i}",
                    "weight_bp": weight,
                    "easy": 1,
                    "medium": 1,
                    "hard": 1,
                    "reasons": [],
                }
            )
        spare_easy = self.question(skill, comps[0], 1)
        spare_medium = self.question(skill, comps[0], 2)
        draft = self.question(skill, comps[0], 1, status="DRAFT", review="NONE")
        retired = self.question(skill, comps[0], 1, status="RETIRED")
        outside_q = self.question(skill, outside, 1)
        bid, fingerprint = self.blueprint(
            skill, entries, count=len(ids), time_limit=time_limit, available=available
        )
        return World(
            skill,
            bid,
            comps,
            ids,
            correct,
            spare_easy,
            spare_medium,
            draft,
            retired,
            outside_q,
            fingerprint,
        )

    def attempt(self, aid: uuid.UUID) -> dict[str, Any]:
        rows = self.run("SELECT * FROM test_attempts WHERE id = :a", a=aid)
        assert len(rows) == 1
        return rows[0]

    def evidence(self, aid: uuid.UUID) -> list[dict[str, Any]]:
        return self.run("SELECT * FROM skill_evidence WHERE attempt_id = :a", a=aid)

    def cleanup(self) -> None:
        with self.engine.begin() as conn:
            conn.execute(text("ALTER TABLE question_bank DISABLE TRIGGER question_bank_immutable"))
            conn.execute(
                text(
                    "ALTER TABLE assessment_blueprints "
                    "DISABLE TRIGGER assessment_blueprints_immutable"
                )
            )
            ids = [
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT id FROM assessment_blueprints "
                        "WHERE id = ANY(:b) OR fingerprint = ANY(:f)"
                    ),
                    {"b": self.blueprints, "f": self.fingerprints},
                )
            ]
            for sql in (
                "DELETE FROM skill_evidence WHERE blueprint_id = ANY(:i)",
                "DELETE FROM test_attempts WHERE blueprint_id = ANY(:i)",
                "DELETE FROM slot_assessments WHERE blueprint_id = ANY(:i)",
                "DELETE FROM assessment_blueprints WHERE id = ANY(:i)",
            ):
                conn.execute(text(sql), {"i": ids})
            conn.execute(
                text("DELETE FROM question_bank WHERE id = ANY(:q)"), {"q": self.questions}
            )
            conn.execute(text("DELETE FROM competencies WHERE id = ANY(:c)"), {"c": self.comps})
            conn.execute(text("ALTER TABLE question_bank ENABLE TRIGGER question_bank_immutable"))
            conn.execute(
                text(
                    "ALTER TABLE assessment_blueprints "
                    "ENABLE TRIGGER assessment_blueprints_immutable"
                )
            )


@pytest.fixture(scope="module")
def mig(migrated: str) -> Iterator[Mig]:
    engine = create_engine(migrated)
    helper = Mig(engine)
    try:
        yield helper
    finally:
        try:
            helper.cleanup()
        finally:
            engine.dispose()


# ------------------------------------------------------------------------------ runtime side


async def make_user(role: str = "DEVELOPER") -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        user = User(
            email=unique_email(role.lower()),
            phone_e164=unique_phone() if role != "ADMIN" else None,
            role=UserRole(role),
            status=UserStatus.ACTIVE,
            display_name="RA",
            password_hash=hash_password("rls test password 1!"),
        )
        db.add(user)
        await db.flush()
        uid = user.id
        await db.commit()
    return uid


async def call(
    user: uuid.UUID | None,
    sql: str,
    params: dict[str, Any] | None = None,
    *,
    role: str = "DEVELOPER",
    system: bool = False,
) -> list[dict[str, Any]]:
    """Run one statement as a user (or GUEST, or SYSTEM on the worker role) and commit."""
    if system:
        ctx = DbContext.system()
    elif user is None:
        ctx = DbContext.guest()
    else:
        ctx = DbContext(user_id=user, role=role)
    async with open_session(ctx, job=system) as db:
        result = await db.execute(text(sql), params or {})
        rows = [dict(r) for r in result.mappings().all()] if result.returns_rows else []
        await db.commit()
    return rows


def sqlstate(exc: DBAPIError) -> str | None:
    """SQLSTATE of a database error (read from the driver, not from app code)."""
    return getattr(exc.orig, "sqlstate", None)


def domain_code(exc: DBAPIError) -> tuple[str | None, dict[str, Any]]:
    """The domain code (message of a P0001 error) and its JSON DETAIL, read from the asyncpg
    exception behind SQLAlchemy's adapter (which has no `diag` attribute)."""
    if sqlstate(exc) != "P0001":
        return None, {}
    cause = exc.orig.__cause__ if exc.orig is not None else None
    message = getattr(cause, "message", None)
    detail = getattr(cause, "detail", None)
    return message, (json.loads(detail) if detail else {})


async def refused(coro: Any, code: str) -> dict[str, Any]:
    """The call raised the domain error `code` (P0001); returns its JSON detail."""
    with pytest.raises(DBAPIError) as info:
        await coro
    got, detail = domain_code(info.value)
    assert got == code, (got, sqlstate(info.value), str(info.value)[:300])
    return detail


async def failed(coro: Any, state: str, match: str | None = None) -> None:
    """The call raised an error with SQLSTATE `state` (and `match` in its message)."""
    with pytest.raises(DBAPIError) as info:
        await coro
    assert sqlstate(info.value) == state, (sqlstate(info.value), str(info.value)[:300])
    if match is not None:
        assert match in str(info.value)


def token() -> bytes:
    return hashlib.sha256(secrets.token_bytes(16)).digest()


START = (
    "SELECT * FROM start_role_attempt(CAST(:bp AS uuid), CAST(:ids AS uuid[]), :now, :seed, "
    "CAST(NULL AS uuid), CAST(NULL AS uuid), :tok, :extra, CAST(1 AS smallint), :retake, "
    "CAST(:ll AS smallint), CAST(:vd AS smallint), false, CAST(:mr AS review_level))"
)


async def start_raw(
    user: uuid.UUID | None,
    blueprint: uuid.UUID,
    ids: list[uuid.UUID],
    *,
    now: datetime = T0,
    tok: bytes | None = None,
    role: str = "DEVELOPER",
    extra: int = 0,
    retake: int = 30,
    leave_limit: int = 2,
    validity: int = 180,
    min_review: str = "SELF_VERIFIED",
) -> list[dict[str, Any]]:
    return await call(
        user,
        START,
        {
            "bp": blueprint,
            "ids": [str(i) for i in ids],
            "now": now,
            "seed": 7,
            "tok": tok or token(),
            "extra": extra,
            "retake": retake,
            "ll": leave_limit,
            "vd": validity,
            "mr": min_review,
        },
        role=role,
    )


@dataclass
class Run:
    """A started role attempt and the calls a client makes on it."""

    mig: Mig
    user: uuid.UUID
    w: World
    aid: uuid.UUID
    tok: bytes
    ids: list[uuid.UUID]
    t0: datetime
    deadline: datetime
    log: list[Any] = field(default_factory=list)

    def choice(self, index: int, ok: bool) -> int:
        right = self.w.correct[self.ids[index]]
        return right if ok else (right + 1) % 4

    async def answer(
        self,
        index: int,
        *,
        ok: bool = True,
        skip: bool = False,
        now: datetime | None = None,
        tok: bytes | None = None,
        question: uuid.UUID | None = None,
        choice: int | None = None,
        user: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        value = None if skip else (choice if choice is not None else self.choice(index, ok))
        rows = await call(
            user or self.user,
            "SELECT * FROM record_role_answer(CAST(:a AS uuid), CAST(:q AS uuid), "
            "CAST(:c AS int), :now, :tok)",
            {
                "a": self.aid,
                "q": question or self.ids[index],
                "c": value,
                "now": now or self.t0,
                "tok": tok if tok is not None else self.tok,
            },
        )
        return rows[0]

    async def answer_all(
        self, plan: list[bool] | None = None, *, now: datetime | None = None
    ) -> str:
        flags = plan or [True] * len(self.ids)
        last = ""
        for i, ok in enumerate(flags):
            row = await self.answer(i, ok=ok, now=now)
            last = row["status"]
        return last

    async def focus(
        self,
        seq: int,
        *,
        now: datetime | None = None,
        kind: str = "VISIBILITY_HIDDEN",
        tok: bytes | None = None,
        client_at: datetime | None = None,
    ) -> dict[str, Any]:
        rows = await call(
            self.user,
            "SELECT * FROM record_focus_event(CAST(:a AS uuid), :seq, :t, :now, :c, "
            "CAST(NULL AS boolean), :tok)",
            {
                "a": self.aid,
                "seq": seq,
                "t": kind,
                "now": now or self.t0,
                "c": client_at,
                "tok": tok if tok is not None else self.tok,
            },
        )
        return rows[0]

    async def heartbeat(self, now: datetime, *, tok: bytes | None = None) -> str:
        rows = await call(
            self.user,
            "SELECT record_heartbeat(CAST(:a AS uuid), :now, :tok) AS r",
            {"a": self.aid, "now": now, "tok": tok if tok is not None else self.tok},
        )
        return str(rows[0]["r"])

    async def current(
        self, *, tok: bytes | None = None, user: uuid.UUID | None = None, role: str = "DEVELOPER"
    ) -> list[dict[str, Any]]:
        return await call(
            user or self.user,
            "SELECT * FROM role_current_question(CAST(:a AS uuid), :tok)",
            {"a": self.aid, "tok": tok if tok is not None else self.tok},
            role=role,
        )

    async def score(
        self, now: datetime, *, user: uuid.UUID | None = None, system: bool = False
    ) -> str:
        rows = await call(
            None if system else (user or self.user),
            "SELECT score_role_attempt(CAST(:a AS uuid), :now) AS r",
            {"a": self.aid, "now": now},
            system=system,
        )
        return str(rows[0]["r"])

    async def rotate(self, now: datetime | None = None) -> bytes:
        new = token()
        rows = await call(
            self.user,
            "SELECT rotate_attempt_token(CAST(:a AS uuid), :t, :now) AS r",
            {"a": self.aid, "t": new, "now": now or self.t0},
        )
        assert rows[0]["r"] == "OK"
        return new

    def row(self) -> dict[str, Any]:
        return self.mig.attempt(self.aid)

    def evidence(self) -> list[dict[str, Any]]:
        return self.mig.evidence(self.aid)

    def after_deadline(self, seconds: float) -> datetime:
        return self.deadline + timedelta(seconds=seconds)


async def begin(
    mig: Mig,
    w: World,
    user: uuid.UUID | None = None,
    *,
    now: datetime = T0,
    ids: list[uuid.UUID] | None = None,
    **kw: Any,
) -> Run:
    uid = user or await make_user()
    chosen = ids or w.ids
    tok = token()
    rows = await start_raw(uid, w.blueprint_id, chosen, now=now, tok=tok, **kw)
    return Run(mig, uid, w, rows[0]["attempt_id"], tok, chosen, now, rows[0]["deadline_at"])


# ============================================================================== start


@pytest.mark.parametrize("role", ["CLIENT", "ADMIN", "GUEST"])
async def test_only_developers_start_role_attempts(mig: Mig, role: str) -> None:
    w = mig.world()
    uid = None if role == "GUEST" else await make_user(role)
    await refused(start_raw(uid, w.blueprint_id, w.ids, role=role), "ROLE_NOT_ALLOWED")
    assert (
        mig.scalar("SELECT count(*) FROM test_attempts WHERE blueprint_id = :b", b=w.blueprint_id)
        == 0
    )


async def test_a_valid_start_creates_one_open_attempt_with_the_right_deadline(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w, extra=120)
    row = run.row()
    assert run.deadline == T0 + timedelta(seconds=LIMIT + 120)
    assert row["kind"] == "ROLE"
    assert row["submitted_at"] is None
    assert row["question_ids"] == w.ids
    assert row["current_index"] == 0
    assert row["answers_locked"] == []
    assert row["focus_leaves"] == 0
    assert row["leave_limit"] == 2
    assert row["extra_time_seconds"] == 120
    assert row["attempt_token_hash"] == run.tok
    assert row["consent_at"] is not None
    assert row["test_id"] is None
    assert row["blueprint_id"] == w.blueprint_id


async def test_start_increments_times_served_for_the_selection_only(mig: Mig) -> None:
    w = mig.world()
    await begin(mig, w)
    rows = mig.run(
        "SELECT id, times_served FROM question_bank WHERE id = ANY(:i)", i=list(w.correct)
    )
    assert {r["times_served"] for r in rows} == {1}
    spare = mig.run(
        "SELECT times_served FROM question_bank WHERE id = ANY(:i)",
        i=[w.spare_easy, w.spare_medium, w.draft_easy, w.outside_easy],
    )
    assert {r["times_served"] for r in spare} == {0}


async def test_a_refused_start_does_not_touch_times_served(mig: Mig) -> None:
    w = mig.world()
    await refused(
        start_raw(await make_user("CLIENT"), w.blueprint_id, w.ids, role="CLIENT"),
        "ROLE_NOT_ALLOWED",
    )
    bad = [*w.ids[:-1], w.draft_easy]
    await failed(start_raw(await make_user(), w.blueprint_id, bad), CHECK_VIOLATION)
    rows = mig.run("SELECT times_served FROM question_bank WHERE id = ANY(:i)", i=list(w.correct))
    assert {r["times_served"] for r in rows} == {0}


def _swapped(ids: list[uuid.UUID], index: int, new: uuid.UUID) -> list[uuid.UUID]:
    out = list(ids)
    out[index] = new
    return out


async def test_selection_with_the_wrong_count_is_refused(mig: Mig) -> None:
    w = mig.world()
    uid = await make_user()
    await failed(start_raw(uid, w.blueprint_id, w.ids[:-1]), CHECK_VIOLATION)
    await failed(start_raw(uid, w.blueprint_id, [*w.ids, w.spare_easy]), CHECK_VIOLATION)
    await failed(start_raw(uid, w.blueprint_id, []), CHECK_VIOLATION)


async def test_selection_with_a_duplicate_is_refused(mig: Mig) -> None:
    w = mig.world()
    await failed(
        start_raw(await make_user(), w.blueprint_id, _swapped(w.ids, 5, w.ids[0])),
        CHECK_VIOLATION,
    )


@pytest.mark.parametrize("kind", ["draft", "retired", "unknown"])
async def test_selection_with_a_question_that_is_not_approved_is_refused(
    mig: Mig, kind: str
) -> None:
    w = mig.world()
    replacement = {"draft": w.draft_easy, "retired": w.retired_easy, "unknown": uuid.uuid4()}[kind]
    await failed(
        start_raw(await make_user(), w.blueprint_id, _swapped(w.ids, 0, replacement)),
        CHECK_VIOLATION,
    )


async def test_selection_with_the_wrong_competency_is_refused(mig: Mig) -> None:
    w = mig.world()
    uid = await make_user()
    # A question of a competency outside the blueprint, in place of comp 0's easy one.
    await failed(
        start_raw(uid, w.blueprint_id, _swapped(w.ids, 0, w.outside_easy)), CHECK_VIOLATION
    )
    # A comp-0 easy question in place of comp 1's easy one (comp 0 now has two, comp 1 none).
    await failed(start_raw(uid, w.blueprint_id, _swapped(w.ids, 3, w.spare_easy)), CHECK_VIOLATION)


async def test_selection_with_the_wrong_difficulty_is_refused(mig: Mig) -> None:
    w = mig.world()
    await failed(
        start_raw(await make_user(), w.blueprint_id, _swapped(w.ids, 0, w.spare_medium)),
        CHECK_VIOLATION,
    )


async def test_selection_below_the_required_review_level_is_refused(mig: Mig) -> None:
    w = mig.world()
    await failed(
        start_raw(await make_user(), w.blueprint_id, w.ids, min_review="HUMAN_APPROVED"),
        CHECK_VIOLATION,
    )


async def test_an_unknown_or_unavailable_blueprint_cannot_be_started(mig: Mig) -> None:
    w = mig.world(available=False)
    uid = await make_user()
    await refused(start_raw(uid, w.blueprint_id, w.ids), "BLUEPRINT_UNAVAILABLE")
    await refused(start_raw(uid, uuid.uuid4(), w.ids), "BLUEPRINT_UNAVAILABLE")


async def test_already_passed_is_refused_with_no_second_attempt(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w)
    assert await first.answer_all() == "SCORED"
    assert first.row()["passed"] is True
    later = T0 + timedelta(days=60)  # past the retake window; the pass is still valid
    await refused(start_raw(first.user, w.blueprint_id, w.ids, now=later), "ALREADY_PASSED")
    assert mig.scalar("SELECT count(*) FROM test_attempts WHERE user_id = :u", u=first.user) == 1


async def test_a_pass_that_has_expired_no_longer_blocks_a_new_start(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w, validity=30)
    await first.answer_all()
    after = T0 + timedelta(days=31)
    run = await begin(mig, w, first.user, now=after, retake=1)
    assert run.row()["submitted_at"] is None


async def test_a_voided_pass_no_longer_blocks_a_new_start(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w)
    await first.answer_all()
    admin = await make_user("ADMIN")
    await call(
        admin,
        "SELECT * FROM void_role_attempt(CAST(:a AS uuid), 'test', :now)",
        {"a": first.aid, "now": T0 + timedelta(hours=1)},
        role="ADMIN",
    )
    run = await begin(mig, w, first.user, now=T0 + timedelta(hours=2))
    assert run.row()["submitted_at"] is None


async def test_attempt_open_carries_json_detail(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w)
    detail = await refused(
        start_raw(first.user, w.blueprint_id, w.ids, now=T0 + timedelta(seconds=10)),
        "ATTEMPT_OPEN",
    )
    assert detail == {
        "attempt_id": str(first.aid),
        "kind": "ROLE",
        "blueprint_id": str(w.blueprint_id),
    }
    # Another blueprint is refused too: one open attempt of any kind.
    other = mig.world()
    detail = await refused(start_raw(first.user, other.blueprint_id, other.ids), "ATTEMPT_OPEN")
    assert detail["attempt_id"] == str(first.aid)


async def test_an_open_practice_attempt_blocks_a_role_start_and_the_reverse(mig: Mig) -> None:
    w = mig.world()
    uid = await make_user()
    test_id = mig.scalar("SELECT id FROM skill_tests WHERE active ORDER BY id LIMIT 1")
    practice = await call(
        uid,
        "SELECT attempt_id FROM start_test_attempt(CAST(:t AS uuid), :now, 1)",
        {"t": test_id, "now": T0},
    )
    detail = await refused(start_raw(uid, w.blueprint_id, w.ids, now=T0), "ATTEMPT_OPEN")
    assert detail["attempt_id"] == str(practice[0]["attempt_id"])
    assert detail["kind"] == "PRACTICE"
    assert detail["blueprint_id"] is None
    # ... and a role attempt blocks a practice start.
    other = await make_user()
    await begin(mig, w, other)
    await failed(
        call(
            other,
            "SELECT attempt_id FROM start_test_attempt(CAST(:t AS uuid), :now, 1)",
            {"t": test_id, "now": T0},
        ),
        UNIQUE_VIOLATION,
    )


async def test_an_abandoned_attempt_past_its_grace_does_not_block(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w)
    inside = first.after_deadline(GRACE - 1)
    await refused(start_raw(first.user, w.blueprint_id, w.ids, now=inside), "ATTEMPT_OPEN")
    outside = first.after_deadline(GRACE + 1)
    rows = await start_raw(first.user, w.blueprint_id, w.ids, now=outside)
    assert rows[0]["attempt_id"] != first.aid


async def test_retake_is_locked_for_thirty_days_after_a_scored_attempt(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w)
    await first.answer_all([False] * 6)
    assert first.row()["passed"] is False
    scored_at = first.row()["submitted_at"]
    unlock = scored_at + timedelta(days=30)
    detail = await refused(
        start_raw(first.user, w.blueprint_id, w.ids, now=T0 + timedelta(days=1)), "RETAKE_LOCKED"
    )
    assert datetime.fromisoformat(detail["next_allowed_at"]) == unlock
    await refused(
        start_raw(first.user, w.blueprint_id, w.ids, now=unlock - timedelta(seconds=1)),
        "RETAKE_LOCKED",
    )
    rows = await start_raw(first.user, w.blueprint_id, w.ids, now=unlock)
    assert rows[0]["attempt_id"] != first.aid


async def test_retake_days_comes_from_the_caller(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w)
    await first.answer_all([False] * 6)
    await refused(
        start_raw(first.user, w.blueprint_id, w.ids, now=T0 + timedelta(days=2), retake=7),
        "RETAKE_LOCKED",
    )
    rows = await start_raw(first.user, w.blueprint_id, w.ids, now=T0 + timedelta(days=2), retake=1)
    assert rows[0]["attempt_id"] != first.aid


async def test_a_terminated_attempt_counts_toward_the_retake_limit(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w)
    await first.focus(1)
    assert (await first.focus(2))["status"] == "TERMINATED"
    await refused(
        start_raw(first.user, w.blueprint_id, w.ids, now=T0 + timedelta(days=1)), "RETAKE_LOCKED"
    )


async def test_a_voided_attempt_does_not_count_toward_the_retake_limit(mig: Mig) -> None:
    w = mig.world()
    first = await begin(mig, w)
    await first.answer_all([False] * 6)
    await refused(
        start_raw(first.user, w.blueprint_id, w.ids, now=T0 + timedelta(days=1)), "RETAKE_LOCKED"
    )
    admin = await make_user("ADMIN")
    rows = await call(
        admin,
        "SELECT * FROM void_role_attempt(CAST(:a AS uuid), 'checked by hand', :now)",
        {"a": first.aid, "now": T0 + timedelta(days=1)},
        role="ADMIN",
    )
    assert len(rows) == 1
    assert mig.evidence(first.aid)[0]["voided_at"] is not None
    retry = await start_raw(first.user, w.blueprint_id, w.ids, now=T0 + timedelta(days=1))
    assert retry[0]["attempt_id"] != first.aid


async def test_the_retake_lock_is_per_blueprint(mig: Mig) -> None:
    w, other = mig.world(), mig.world()
    first = await begin(mig, w)
    await first.answer_all([False] * 6)
    run = await begin(mig, other, first.user, now=T0 + timedelta(days=1))
    assert run.row()["blueprint_id"] == other.blueprint_id


async def test_concurrent_starts_create_exactly_one_attempt(mig: Mig) -> None:
    w = mig.world()
    uid = await make_user()
    results = await asyncio.gather(
        start_raw(uid, w.blueprint_id, w.ids),
        start_raw(uid, w.blueprint_id, w.ids),
        return_exceptions=True,
    )
    wins = [r for r in results if isinstance(r, list)]
    losses = [r for r in results if isinstance(r, DBAPIError)]
    assert len(wins) == 1, results
    assert len(losses) == 1, results
    assert domain_code(losses[0])[0] == "ATTEMPT_OPEN"
    assert mig.scalar("SELECT count(*) FROM test_attempts WHERE user_id = :u", u=uid) == 1
    rows = mig.run("SELECT times_served FROM question_bank WHERE id = ANY(:i)", i=list(w.correct))
    assert {r["times_served"] for r in rows} == {1}


async def test_many_parallel_starts_still_create_one_attempt(mig: Mig) -> None:
    w = mig.world()
    uid = await make_user()
    results = await asyncio.gather(
        *(start_raw(uid, w.blueprint_id, w.ids) for _ in range(5)), return_exceptions=True
    )
    assert sum(isinstance(r, list) for r in results) == 1
    assert mig.scalar("SELECT count(*) FROM test_attempts WHERE user_id = :u", u=uid) == 1


# ============================================================================== current question


async def test_current_question_returns_only_the_current_one_and_never_the_answer(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    rows = await run.current()
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == {
        "idx",
        "total",
        "question_id",
        "text",
        "code_snippet",
        "options",
        "competency_name",
    }
    assert not any("correct" in key or "answer" in key for key in row)
    assert (row["idx"], row["total"], row["question_id"]) == (0, 6, w.ids[0])
    assert row["options"] == ["opt a", "opt b", "opt c", "opt d"]
    assert row["competency_name"].startswith("RT competency")
    await run.answer(0)
    nxt = (await run.current())[0]
    assert (nxt["idx"], nxt["question_id"]) == (1, w.ids[1])


async def test_current_question_is_for_the_owner_with_the_current_token_only(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    other = await make_user()
    await failed(run.current(user=other), NO_DATA)
    await failed(run.current(user=await make_user("CLIENT"), role="CLIENT"), NO_DATA)
    await refused(run.current(tok=token()), "ATTEMPT_TOKEN_INVALID")
    await refused(run.current(tok=b""), "ATTEMPT_TOKEN_INVALID")


async def test_current_question_without_a_token_is_refused(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await refused(
        call(
            run.user,
            "SELECT * FROM role_current_question(CAST(:a AS uuid), CAST(NULL AS bytea))",
            {"a": run.aid},
        ),
        "ATTEMPT_TOKEN_REQUIRED",
    )


async def test_current_question_is_empty_once_scored(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer_all()
    assert await run.current() == []


# ============================================================================== answers


async def test_an_answer_for_another_question_is_not_the_current_question(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await refused(run.answer(1), "NOT_CURRENT_QUESTION")  # ahead
    await refused(run.answer(0, question=uuid.uuid4()), "NOT_CURRENT_QUESTION")  # unknown
    await refused(run.answer(0, question=w.spare_easy), "NOT_CURRENT_QUESTION")  # not in attempt
    row = run.row()
    assert row["current_index"] == 0
    assert row["answers_locked"] == []


async def test_an_old_question_after_moving_on_is_not_the_current_question(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer(0)
    await run.answer(1)
    await refused(run.answer(0), "NOT_CURRENT_QUESTION")
    assert run.row()["current_index"] == 2


async def test_an_identical_retry_is_a_duplicate_and_changes_nothing(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    first = await run.answer(0, ok=False)
    assert first == {"status": "NEXT", "current_index": 1}
    again = await run.answer(0, ok=False)
    assert again == {"status": "DUPLICATE", "current_index": 1}
    row = run.row()
    assert row["current_index"] == 1
    assert len(row["answers_locked"]) == 1
    assert row["answers_locked"][0]["choice"] == run.choice(0, False)


async def test_a_changed_retry_is_not_the_current_question(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer(0, ok=False)
    await refused(run.answer(0, ok=True), "NOT_CURRENT_QUESTION")
    assert run.row()["answers_locked"][0]["choice"] == run.choice(0, False)


async def test_a_retry_of_a_skip_is_a_duplicate(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    assert (await run.answer(0, skip=True))["status"] == "NEXT"
    again = await run.answer(0, skip=True)
    assert again["status"] == "DUPLICATE"
    assert len(run.row()["answers_locked"]) == 1


async def test_a_skip_locks_the_question_and_counts_as_wrong(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer(0, skip=True)
    row = run.row()
    assert row["answers_locked"][0]["choice"] is None
    assert row["current_index"] == 1
    await refused(run.answer(0, ok=True), "NOT_CURRENT_QUESTION")


@pytest.mark.parametrize("bad", [4, -1, 99])
async def test_an_invalid_choice_is_refused(mig: Mig, bad: int) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await failed(run.answer(0, choice=bad), CHECK_VIOLATION)
    assert run.row()["current_index"] == 0


async def test_the_last_answer_scores_the_attempt(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    for i in range(5):
        assert (await run.answer(i))["status"] == "NEXT"
    last = await run.answer(5, now=T0 + timedelta(seconds=300))
    assert last == {"status": "SCORED", "current_index": 6}
    row = run.row()
    assert row["submitted_at"] == T0 + timedelta(seconds=300)
    assert row["overall_bp"] == 10000
    assert row["passed"] is True
    assert row["terminated_reason"] is None
    assert len(run.evidence()) == 1


async def test_answers_after_scoring_are_closed(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer_all()
    assert (await run.answer(0))["status"] == "CLOSED"
    assert len(run.row()["answers_locked"]) == 6
    assert len(run.evidence()) == 1


async def test_grace_accepts_the_answer_four_seconds_after_the_deadline(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    row = await run.answer(0, now=run.after_deadline(4))
    assert row["status"] == "NEXT"
    assert run.row()["submitted_at"] is None
    assert len(run.row()["answers_locked"]) == 1


async def test_grace_ends_five_seconds_after_the_deadline(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    assert (await run.answer(0, now=run.after_deadline(5)))["status"] == "NEXT"
    expired = await run.answer(1, now=run.after_deadline(5.001))
    assert expired["status"] == "EXPIRED"
    assert run.row()["submitted_at"] is not None


async def test_an_answer_six_seconds_late_is_refused_and_the_attempt_is_scored(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer(0, now=T0 + timedelta(seconds=10))
    late = run.after_deadline(6)
    row = await run.answer(1, now=late)
    assert row["status"] == "EXPIRED"
    state = run.row()
    assert state["submitted_at"] == late
    assert len(state["answers_locked"]) == 1  # the late answer was not locked
    assert state["terminated_reason"] is None  # answered something: not "abandoned"
    assert state["passed"] is False
    evidence = run.evidence()
    assert len(evidence) == 1
    assert evidence[0]["passed"] is False
    assert (await run.answer(1, now=late))["status"] == "CLOSED"


async def test_expiry_scores_unanswered_questions_as_wrong(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    for i in range(3):  # competency 0 entirely right, competency 1 never reached
        await run.answer(i, now=T0 + timedelta(seconds=30 * (i + 1)))
    await run.answer(3, now=run.after_deadline(10))
    row = run.row()
    assert [c["score_bp"] for c in row["breakdown"]] == [10000, 0]
    assert row["overall_bp"] == 5000
    assert row["passed"] is False


async def test_answers_check_owner_and_token(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await failed(run.answer(0, user=await make_user()), NO_DATA)
    await refused(run.answer(0, tok=token()), "ATTEMPT_TOKEN_INVALID")
    await refused(run.answer(0, tok=b""), "ATTEMPT_TOKEN_INVALID")
    assert run.row()["current_index"] == 0


async def test_a_retired_token_is_moved_after_rotation(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    old = run.tok
    new = await run.rotate()
    assert new != old
    await refused(run.answer(0, tok=old), "ATTEMPT_MOVED")
    await refused(run.focus(1, tok=old), "ATTEMPT_MOVED")
    await refused(run.heartbeat(T0, tok=old), "ATTEMPT_MOVED")
    await refused(run.current(tok=old), "ATTEMPT_MOVED")
    assert run.row()["focus_leaves"] == 0
    assert (await run.answer(0, tok=new))["status"] == "NEXT"
    assert (await run.current(tok=new))[0]["idx"] == 1
    # Still-unknown tokens stay "invalid", not "moved".
    await refused(run.answer(1, tok=token()), "ATTEMPT_TOKEN_INVALID")


async def test_rotating_twice_retires_both_earlier_tokens(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    first = run.tok
    second = await run.rotate()
    third = await run.rotate()
    await refused(run.current(tok=first), "ATTEMPT_MOVED")
    await refused(run.current(tok=second), "ATTEMPT_MOVED")
    assert len(await run.current(tok=third)) == 1


async def test_rotate_is_for_the_owner_and_an_open_attempt(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    stranger = await make_user()
    await failed(
        call(
            stranger,
            "SELECT rotate_attempt_token(CAST(:a AS uuid), :t, :now)",
            {"a": run.aid, "t": token(), "now": T0},
        ),
        NO_DATA,
    )
    assert run.row()["attempt_token_hash"] == run.tok
    await run.answer_all()
    rows = await call(
        run.user,
        "SELECT rotate_attempt_token(CAST(:a AS uuid), :t, :now) AS r",
        {"a": run.aid, "t": token(), "now": T0},
    )
    assert rows[0]["r"] == "CLOSED"


async def test_rotating_after_the_deadline_scores_the_attempt(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    rows = await call(
        run.user,
        "SELECT rotate_attempt_token(CAST(:a AS uuid), :t, :now) AS r",
        {"a": run.aid, "t": token(), "now": run.after_deadline(6)},
    )
    assert rows[0]["r"] == "EXPIRED"
    assert run.row()["submitted_at"] is not None


async def test_concurrent_answers_to_the_same_question_let_one_win(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    results = await asyncio.gather(
        run.answer(0, ok=True), run.answer(0, ok=False), return_exceptions=True
    )
    wins = [r for r in results if isinstance(r, dict)]
    losses = [r for r in results if isinstance(r, DBAPIError)]
    assert len(wins) == 1, results
    assert wins[0]["status"] == "NEXT"
    assert len(losses) == 1
    assert domain_code(losses[0])[0] == "NOT_CURRENT_QUESTION"
    row = run.row()
    assert row["current_index"] == 1
    assert len(row["answers_locked"]) == 1


async def test_concurrent_identical_answers_count_once(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    a, b = await asyncio.gather(run.answer(0), run.answer(0))
    assert sorted([a["status"], b["status"]]) == ["DUPLICATE", "NEXT"]
    assert len(run.row()["answers_locked"]) == 1


async def test_concurrent_last_answers_score_once(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    for i in range(5):
        await run.answer(i)
    a, b = await asyncio.gather(run.answer(5), run.answer(5))
    # The loser sees the attempt already closed (or a retry of the answer that scored it).
    assert sorted([a["status"], b["status"]])[1] == "SCORED"
    assert {a["status"], b["status"]} - {"SCORED"} <= {"CLOSED", "DUPLICATE"}
    assert len(run.evidence()) == 1


async def test_finish_early_counts_the_rest_as_wrong_and_is_idempotent(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer(0)
    await run.answer(1)
    now = T0 + timedelta(seconds=60)
    args = {"a": run.aid, "now": now, "tok": run.tok}
    sql = "SELECT finish_role_attempt(CAST(:a AS uuid), :now, :tok) AS r"
    assert (await call(run.user, sql, args))[0]["r"] == "SCORED"
    assert (await call(run.user, sql, args))[0]["r"] == "CLOSED"
    row = run.row()
    assert row["passed"] is False
    assert [c["possible_w"] for c in row["breakdown"]] == [9, 9]
    assert [c["earned_w"] for c in row["breakdown"]] == [5, 0]
    assert len(run.evidence()) == 1


# ============================================================================== focus events


async def test_a_first_leave_is_a_warning_and_a_retry_is_a_duplicate(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    assert await run.focus(1) == {"status": "WARNING", "focus_leaves": 1}
    assert await run.focus(1) == {"status": "DUPLICATE", "focus_leaves": 1}
    row = run.row()
    assert (row["focus_leaves"], row["last_focus_seq"], len(row["focus_events"])) == (1, 1, 1)
    event = row["focus_events"][0]
    assert (event["seq"], event["type"]) == (1, "VISIBILITY_HIDDEN")
    assert row["submitted_at"] is None


async def test_focus_seq_at_or_below_the_last_is_a_duplicate_and_cannot_lower_the_count(
    mig: Mig,
) -> None:
    w = mig.world()
    run = await begin(mig, w, leave_limit=5)
    assert (await run.focus(3))["focus_leaves"] == 1  # seq may skip numbers
    assert await run.focus(2) == {"status": "DUPLICATE", "focus_leaves": 1}
    assert await run.focus(3) == {"status": "DUPLICATE", "focus_leaves": 1}
    assert await run.focus(1) == {"status": "DUPLICATE", "focus_leaves": 1}
    assert (await run.focus(4))["focus_leaves"] == 2
    row = run.row()
    assert (row["focus_leaves"], row["last_focus_seq"]) == (2, 4)


async def test_the_second_leave_terminates_even_when_every_answer_was_right(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    for i in range(5):  # five right answers, one question left
        await run.answer(i)
    assert (await run.focus(1))["status"] == "WARNING"
    now = T0 + timedelta(seconds=100)
    assert await run.focus(2, now=now) == {"status": "TERMINATED", "focus_leaves": 2}
    row = run.row()
    assert row["overall_bp"] >= RULE["overall_bp"]  # the score alone would have passed
    assert row["passed"] is False
    assert row["flagged"] is True
    assert row["terminated_reason"] == "FOCUS_LIMIT"
    assert row["submitted_at"] == now
    evidence = run.evidence()
    assert len(evidence) == 1
    assert evidence[0]["passed"] is False
    assert evidence[0]["valid_until"] is None


async def test_the_leave_limit_comes_from_the_start_call(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w, leave_limit=3)
    assert (await run.focus(1))["status"] == "WARNING"
    assert (await run.focus(2))["status"] == "WARNING"
    assert (await run.focus(3))["status"] == "TERMINATED"
    one = await begin(mig, mig.world(), leave_limit=1)
    assert (await one.focus(1))["status"] == "TERMINATED"


async def test_focus_events_are_stored_boundedly_but_the_count_keeps_going(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w, leave_limit=100)
    async with open_session(DbContext(user_id=run.user, role="DEVELOPER")) as db:
        for seq in range(1, 41):
            result = await db.execute(
                text(
                    "SELECT * FROM record_focus_event(CAST(:a AS uuid), :s, 'WINDOW_BLUR', :now, "
                    "CAST(NULL AS timestamptz), CAST(NULL AS boolean), :tok)"
                ),
                {"a": run.aid, "s": seq, "now": T0 + timedelta(seconds=seq), "tok": run.tok},
            )
            assert result.mappings().one()["status"] == "WARNING"
        await db.commit()
    row = run.row()
    assert row["focus_leaves"] == 40
    assert row["last_focus_seq"] == 40
    assert len(row["focus_events"]) == 30
    assert [e["seq"] for e in row["focus_events"]] == list(range(1, 31))


async def test_focus_events_after_scoring_are_closed_and_change_nothing(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer_all()
    before = run.row()
    assert await run.focus(1) == {"status": "CLOSED", "focus_leaves": 0}
    assert await run.focus(500) == {"status": "CLOSED", "focus_leaves": 0}  # even a bad seq
    after = run.row()
    assert (after["focus_leaves"], after["flagged"], after["passed"]) == (
        before["focus_leaves"],
        before["flagged"],
        before["passed"],
    )
    assert after["terminated_reason"] is None


async def test_focus_after_a_termination_is_closed(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.focus(1)
    await run.focus(2)
    assert await run.focus(3) == {"status": "CLOSED", "focus_leaves": 2}
    assert run.row()["focus_leaves"] == 2


@pytest.mark.parametrize(
    ("seq", "kind"),
    [
        (0, "VISIBILITY_HIDDEN"),
        (-1, "VISIBILITY_HIDDEN"),
        (101, "VISIBILITY_HIDDEN"),
        (1, "NOT_A_TYPE"),
        (1, ""),
        (1, "visibility_hidden"),
    ],
)
async def test_invalid_focus_events_are_refused(mig: Mig, seq: int, kind: str) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await failed(run.focus(seq, kind=kind), CHECK_VIOLATION)
    row = run.row()
    assert (row["focus_leaves"], row["last_focus_seq"], row["focus_events"]) == (0, 0, [])


@pytest.mark.parametrize(
    "kind", ["VISIBILITY_HIDDEN", "FULLSCREEN_EXIT", "WINDOW_BLUR", "PAGE_UNLOAD"]
)
async def test_every_documented_focus_type_is_accepted(mig: Mig, kind: str) -> None:
    w = mig.world()
    run = await begin(mig, w)
    client_at = T0 - timedelta(seconds=2)
    assert (await run.focus(1, kind=kind, client_at=client_at))["status"] == "WARNING"
    event = run.row()["focus_events"][0]
    assert event["type"] == kind
    assert datetime.fromisoformat(event["client_at"]) == client_at


async def test_focus_events_check_owner_and_token(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await refused(run.focus(1, tok=token()), "ATTEMPT_TOKEN_INVALID")
    await failed(
        call(
            await make_user(),
            "SELECT * FROM record_focus_event(CAST(:a AS uuid), 1, 'WINDOW_BLUR', :now, "
            "CAST(NULL AS timestamptz), CAST(NULL AS boolean), :tok)",
            {"a": run.aid, "now": T0, "tok": run.tok},
        ),
        NO_DATA,
    )
    assert run.row()["focus_leaves"] == 0


async def test_a_leave_after_the_deadline_scores_the_attempt_as_expired_not_terminated(
    mig: Mig,
) -> None:
    w = mig.world()
    run = await begin(mig, w)
    out = await run.focus(1, now=run.after_deadline(6))
    assert out["status"] == "EXPIRED"
    row = run.row()
    assert row["submitted_at"] is not None
    assert row["focus_leaves"] == 0
    assert row["terminated_reason"] == "EXPIRED"  # no answers at all


# ============================================================================== heartbeats


async def test_gaps_over_a_minute_are_counted_and_over_two_minutes_flag(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    assert await run.heartbeat(T0 + timedelta(seconds=60)) == "OK"
    assert run.row()["connection_gaps"] == 0  # exactly 60 s is not a gap
    await run.heartbeat(T0 + timedelta(seconds=121))  # 61 s
    row = run.row()
    assert (row["connection_gaps"], row["flagged"]) == (1, False)
    await run.heartbeat(T0 + timedelta(seconds=241))  # exactly 120 s: a gap, not yet a flag
    row = run.row()
    assert (row["connection_gaps"], row["flagged"]) == (2, False)
    await run.heartbeat(T0 + timedelta(seconds=362))  # 121 s
    row = run.row()
    assert (row["connection_gaps"], row["flagged"]) == (3, True)
    assert row["submitted_at"] is None  # gaps never end the attempt
    assert row["terminated_reason"] is None
    assert len(await run.current()) == 1


async def test_regular_heartbeats_leave_no_gap(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    for k in range(1, 20):
        await run.heartbeat(T0 + timedelta(seconds=15 * k))
    row = run.row()
    assert (row["connection_gaps"], row["flagged"]) == (0, False)


async def test_a_late_old_heartbeat_does_not_move_the_clock_back(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.heartbeat(T0 + timedelta(seconds=50))
    await run.heartbeat(T0 + timedelta(seconds=10))
    assert run.row()["last_heartbeat_at"] == T0 + timedelta(seconds=50)


async def test_any_request_measures_the_gap_not_only_heartbeats(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer(0, now=T0 + timedelta(seconds=200))
    row = run.row()
    assert (row["connection_gaps"], row["flagged"]) == (1, True)
    assert row["current_index"] == 1


async def test_a_gap_never_ends_the_attempt_and_answers_still_work_afterwards(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.heartbeat(T0 + timedelta(seconds=600))
    assert run.row()["flagged"] is True
    assert await run.answer_all(now=T0 + timedelta(seconds=620)) == "SCORED"
    assert run.row()["passed"] is True  # flagged for review, not failed


async def test_a_heartbeat_after_scoring_is_closed_and_after_the_deadline_expires(mig: Mig) -> None:
    w = mig.world()
    done = await begin(mig, w)
    await done.answer_all()
    assert await done.heartbeat(T0 + timedelta(seconds=30)) == "CLOSED"
    open_run = await begin(mig, w)
    assert await open_run.heartbeat(open_run.after_deadline(6)) == "EXPIRED"
    assert open_run.row()["submitted_at"] is not None


async def test_heartbeat_checks_owner_and_token(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await refused(run.heartbeat(T0, tok=token()), "ATTEMPT_TOKEN_INVALID")
    await failed(
        call(
            await make_user(),
            "SELECT record_heartbeat(CAST(:a AS uuid), :now, :tok)",
            {"a": run.aid, "now": T0, "tok": run.tok},
        ),
        NO_DATA,
    )


async def test_the_final_gap_is_measured_when_the_attempt_is_scored(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    assert await run.score(run.after_deadline(10), system=True) == "SCORED"
    row = run.row()
    assert row["connection_gaps"] == 1  # silence from the start to the deadline
    assert row["flagged"] is True


# ============================================================================== scoring


async def test_scoring_is_refused_until_the_grace_has_passed(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await refused(run.score(T0 + timedelta(seconds=1)), "INVALID_STATE")
    await refused(run.score(run.deadline), "INVALID_STATE")
    await refused(run.score(run.after_deadline(GRACE)), "INVALID_STATE")
    await refused(run.score(run.after_deadline(GRACE), system=True), "INVALID_STATE")
    assert run.row()["submitted_at"] is None
    assert await run.score(run.after_deadline(GRACE + 0.001)) == "SCORED"
    assert run.row()["submitted_at"] is not None


async def test_scoring_by_the_system_role_works_after_the_deadline(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    assert await run.score(run.after_deadline(60), system=True) == "SCORED"
    assert run.row()["scored"] is True


async def test_scoring_is_for_the_owner_or_system_only(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    late = run.after_deadline(60)
    await failed(run.score(late, user=await make_user()), NO_DATA)
    stranger = await make_user("CLIENT")
    await failed(
        call(
            stranger,
            "SELECT score_role_attempt(CAST(:a AS uuid), :now)",
            {"a": run.aid, "now": late},
            role="CLIENT",
        ),
        NO_DATA,
    )
    # The web role claiming SYSTEM gains nothing (is the worker role only).
    await failed(
        call(
            None,
            "SELECT score_role_attempt(CAST(:a AS uuid), :now)",
            {"a": run.aid, "now": late},
            role="SYSTEM",
        ),
        NO_DATA,
    )
    assert run.row()["submitted_at"] is None


async def test_scoring_twice_is_idempotent_with_one_evidence_row(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    late = run.after_deadline(60)
    assert await run.score(late) == "SCORED"
    first = run.row()
    assert await run.score(late + timedelta(hours=1)) == "CLOSED"
    assert await run.score(late + timedelta(hours=2), system=True) == "CLOSED"
    second = run.row()
    for key in ("submitted_at", "overall_bp", "passed", "breakdown", "score", "terminated_reason"):
        assert first[key] == second[key], key
    assert len(run.evidence()) == 1


async def test_scoring_after_the_last_answer_is_a_no_op(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer_all()
    assert await run.score(run.after_deadline(60)) == "CLOSED"
    assert len(run.evidence()) == 1


async def test_evidence_of_a_pass(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w, validity=45)
    done_at = T0 + timedelta(seconds=240)
    for i in range(6):
        await run.answer(i, now=done_at)
    evidence = run.evidence()
    assert len(evidence) == 1
    e = evidence[0]
    assert str(e["source"]) == "ROLE_ASSESSMENT"
    assert e["user_id"] == run.user
    assert e["skill_id"] == w.skill_id
    assert e["blueprint_id"] == w.blueprint_id
    assert e["attempt_id"] == run.aid
    assert e["passed"] is True
    assert e["score"] == Decimal("1.000")
    assert e["at"] == done_at
    assert e["valid_until"] == done_at + timedelta(days=45)
    assert e["voided_at"] is None


async def test_evidence_of_a_fail_has_no_validity(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer_all([False] * 6)
    e = run.evidence()[0]
    assert (e["passed"], e["valid_until"], e["score"]) == (False, None, Decimal("0.000"))
    assert str(e["source"]) == "ROLE_ASSESSMENT"
    assert e["blueprint_id"] == w.blueprint_id


async def test_evidence_score_is_rounded_down_to_three_decimals(mig: Mig) -> None:
    w = mig.world(weights=(10000,))
    run = await begin(mig, w)
    await run.answer_all([True, False, True])  # earned 6 of 9 → 6666 bp → 0.666
    row = run.row()
    assert row["overall_bp"] == 6666
    assert run.evidence()[0]["score"] == Decimal("0.666")
    assert row["score"] == Decimal("0.666")


async def test_an_expired_attempt_with_no_answers_is_marked_expired(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    assert await run.score(run.after_deadline(30), system=True) == "SCORED"
    row = run.row()
    assert row["terminated_reason"] == "EXPIRED"
    assert (row["passed"], row["overall_bp"]) == (False, 0)
    e = run.evidence()[0]
    assert (e["passed"], e["valid_until"]) == (False, None)


async def test_an_expired_attempt_with_answers_has_no_terminated_reason(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer(0, now=T0 + timedelta(seconds=20))
    await run.score(run.after_deadline(30), system=True)
    row = run.row()
    assert row["terminated_reason"] is None
    assert row["passed"] is False
    assert row["flagged"] is True  # a long silence before the deadline


async def test_the_breakdown_has_one_entry_per_competency_in_blueprint_order(mig: Mig) -> None:
    w = mig.world(weights=(6000, 4000))
    run = await begin(mig, w)
    await run.answer_all([True, True, True, True, False, False])
    row = run.row()
    assert [str(c["competency_id"]) for c in row["breakdown"]] == [str(c) for c in w.comps]
    assert [c["weight_bp"] for c in row["breakdown"]] == [6000, 4000]
    assert [c["score_bp"] for c in row["breakdown"]] == [10000, 2222]  # 2 of 9
    assert row["overall_bp"] == (6000 * 10000 + 4000 * 2222) // 10000


async def test_the_heavy_competency_floor_is_enforced(mig: Mig) -> None:
    w = mig.world(weights=(8000, 2000))  # 20 % is heavy
    run = await begin(mig, w)
    await run.answer_all([True, True, True, False, False, False])
    row = run.row()
    assert row["overall_bp"] == 8000  # clears the overall bar ...
    assert row["passed"] is False  # ... but not the floor of the heavy 20 % one


async def test_a_light_competency_at_zero_can_still_pass(mig: Mig) -> None:
    w = mig.world(weights=(8500, 1500))
    run = await begin(mig, w)
    await run.answer_all([True, True, True, False, False, False])
    row = run.row()
    assert row["overall_bp"] == 8500
    assert row["passed"] is True


# ============================================================================== SQL ↔ Python


def _vectors() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(VECTORS.read_text(encoding="utf-8"))["vectors"]
    return data


@pytest.mark.parametrize("vector", _vectors(), ids=lambda v: v["name"])
async def test_sql_scoring_matches_the_shared_python_vectors(
    mig: Mig, vector: dict[str, Any]
) -> None:
    skill = mig.any_skill()
    tag = uuid.uuid4().hex[:10]
    comp_ids: dict[str, uuid.UUID] = {}
    entries: list[dict[str, Any]] = []
    for i, c in enumerate(vector["competencies"]):
        comp_ids[c["id"]] = mig.competency(skill, f"{tag}{i}")
        entries.append(
            {
                "competency_id": str(comp_ids[c["id"]]),
                "code": c["code"],
                "name": c["code"],
                "weight_bp": c["weight_bp"],
                "easy": 0,
                "medium": 0,
                "hard": 0,
                "reasons": [],
            }
        )
    rule = {
        "overall_bp": vector["rule"]["pass_overall_bp"],
        "floor_bp": vector["rule"]["floor_bp"],
        "heavy_weight_bp": vector["rule"]["heavy_weight_bp"],
    }
    blueprint, _ = mig.blueprint(skill, entries, count=len(vector["questions"]), rule=rule)
    qids: list[uuid.UUID] = []
    locked: list[dict[str, Any]] = []
    for q in vector["questions"]:
        qid = mig.question(skill, comp_ids[q["competency"]], q["difficulty"], correct=1)
        qids.append(qid)
        locked.append(
            {
                "question_id": str(qid),
                "choice": 1 if q["correct"] else 2,
                "answered_at": T0.isoformat(),
            }
        )
    uid = await make_user()
    started = datetime.now(UTC) - timedelta(hours=2)
    aid = mig.scalar(
        "INSERT INTO test_attempts (kind, blueprint_id, user_id, question_ids, answers, seed, "
        "started_at, deadline_at, scored, consent_at, answers_locked, attempt_token_hash, "
        "validity_days, leave_limit, current_index, last_heartbeat_at) "
        "VALUES ('ROLE', :b, :u, :q, '{}'::jsonb, 1, :s, :d, true, :s, CAST(:l AS jsonb), "
        ":t, 180, 2, :n, :d) RETURNING id",
        b=blueprint,
        u=uid,
        q=qids,
        s=started,
        d=started + timedelta(seconds=LIMIT),
        l=json.dumps(locked),
        t=token(),
        n=len(qids),
    )
    expect = vector["expect"]
    if vector["ended_early"]:
        # Terminated or voided: the same core, reached with a reason (a focus-limit ending).
        mig.run("SELECT role_score_core(:a, now(), 'FOCUS_LIMIT')", a=aid)
    else:
        await call(
            None,
            "SELECT score_role_attempt(CAST(:a AS uuid), now())",
            {"a": aid},
            system=True,
        )
    row = mig.attempt(aid)
    assert row["submitted_at"] is not None
    assert row["overall_bp"] == expect["overall_bp"]
    assert row["passed"] is expect["passed"]
    assert row["score"] == Decimal(expect["score"])
    assert [c["score_bp"] for c in row["breakdown"]] == expect["score_bp"]
    evidence = mig.evidence(aid)
    assert len(evidence) == 1
    assert evidence[0]["passed"] is expect["passed"]
    assert evidence[0]["score"] == Decimal(expect["score"])


def test_there_are_at_least_thirty_shared_vectors() -> None:
    assert len(_vectors()) >= 30


# ============================================================================== triggers


async def test_approved_question_content_is_immutable(mig: Mig) -> None:
    w = mig.world()
    q = w.ids[0]
    other_comp = w.comps[1]
    changes = {
        "text": ("text = 'a changed question text'", {}),
        "options": ("options = CAST(:v AS jsonb)", {"v": json.dumps(["w", "x", "y", "z"])}),
        "correct_index": ("correct_index = 3", {}),
        "code_snippet": ("code_snippet = 'print(1)'", {}),
        "competency_id": ("competency_id = :v", {"v": other_comp}),
        "difficulty": ("difficulty = 3", {}),
        "slug": ("slug = 'rt-renamed-' || id::text", {}),
        "version": ("version = version + 1", {}),
    }
    for name, (assignment, params) in changes.items():
        with pytest.raises(DBAPIError, match="immutable") as info:
            mig.run(f"UPDATE question_bank SET {assignment} WHERE id = :q", q=q, **params)  # noqa: S608
        assert sqlstate(info.value) == INSUFFICIENT, name
    row = mig.run("SELECT text, correct_index, difficulty FROM question_bank WHERE id = :q", q=q)[0]
    assert row["correct_index"] == w.correct[q]


async def test_review_fields_exposure_and_retirement_are_allowed_on_approved_questions(
    mig: Mig,
) -> None:
    w = mig.world()
    q = w.spare_easy
    mig.run(
        "UPDATE question_bank SET review_level = 'HUMAN_APPROVED', reviewed_by_name = 'Reviewer', "
        "reviewed_at = now(), verification = CAST(:v AS jsonb), times_served = times_served + 5 "
        "WHERE id = :q",
        q=q,
        v=json.dumps({"method": "execution"}),
    )
    row = mig.run("SELECT * FROM question_bank WHERE id = :q", q=q)[0]
    assert str(row["review_level"]) == "HUMAN_APPROVED"
    assert row["times_served"] == 5
    mig.run("UPDATE question_bank SET status = 'RETIRED' WHERE id = :q", q=q)
    assert (
        str(mig.run("SELECT status FROM question_bank WHERE id = :q", q=q)[0]["status"])
        == "RETIRED"
    )


async def test_a_retired_question_cannot_come_back_or_change(mig: Mig) -> None:
    w = mig.world()
    q = w.retired_easy
    with pytest.raises(DBAPIError, match="can only be retired") as info:
        mig.run("UPDATE question_bank SET status = 'APPROVED' WHERE id = :q", q=q)
    assert sqlstate(info.value) == INSUFFICIENT
    with pytest.raises(DBAPIError, match="immutable"):
        mig.run("UPDATE question_bank SET text = 'changed after retirement' WHERE id = :q", q=q)


async def test_an_approved_question_cannot_go_back_to_draft(mig: Mig) -> None:
    w = mig.world()
    with pytest.raises(DBAPIError, match="can only be retired"):
        mig.run("UPDATE question_bank SET status = 'DRAFT' WHERE id = :q", q=w.spare_easy)


async def test_approved_and_retired_questions_cannot_be_deleted_but_drafts_can(mig: Mig) -> None:
    w = mig.world()
    for q in (w.spare_easy, w.retired_easy):
        with pytest.raises(DBAPIError, match="are kept") as info:
            mig.run("DELETE FROM question_bank WHERE id = :q", q=q)
        assert sqlstate(info.value) == INSUFFICIENT
    mig.run(
        "UPDATE question_bank SET text = 'a draft may still be edited' WHERE id = :q",
        q=w.draft_easy,
    )
    mig.run("DELETE FROM question_bank WHERE id = :q", q=w.draft_easy)
    assert mig.scalar("SELECT count(*) FROM question_bank WHERE id = :q", q=w.draft_easy) == 0


async def test_the_runtime_admin_role_is_held_to_the_same_triggers(mig: Mig) -> None:
    w = mig.world()
    admin = await make_user("ADMIN")
    await failed(
        call(
            admin,
            "UPDATE question_bank SET correct_index = 3 WHERE id = :q",
            {"q": w.ids[0]},
            role="ADMIN",
        ),
        INSUFFICIENT,
        "immutable",
    )
    await failed(
        call(admin, "DELETE FROM question_bank WHERE id = :q", {"q": w.ids[0]}, role="ADMIN"),
        INSUFFICIENT,
        "are kept",
    )


async def test_blueprints_cannot_be_updated_or_deleted(mig: Mig) -> None:
    w = mig.world()
    for sql in (
        "UPDATE assessment_blueprints SET label = 'changed' WHERE id = :b",
        "UPDATE assessment_blueprints SET question_count = 5 WHERE id = :b",
        "UPDATE assessment_blueprints SET pass_rule = '{}'::jsonb WHERE id = :b",
        "DELETE FROM assessment_blueprints WHERE id = :b",
    ):
        with pytest.raises(DBAPIError, match="immutable") as info:
            mig.run(sql, b=w.blueprint_id)
        assert sqlstate(info.value) == INSUFFICIENT, sql
    assert (
        mig.scalar("SELECT label FROM assessment_blueprints WHERE id = :b", b=w.blueprint_id)
        == "RT role"
    )


async def test_blueprints_are_immutable_for_every_runtime_role(mig: Mig) -> None:
    w = mig.world()
    admin = await make_user("ADMIN")
    for uid, role in ((admin, "ADMIN"), (await make_user(), "DEVELOPER")):
        # Refused by the trigger, by missing privileges or hidden by row security: in every case
        # the row is unchanged.
        try:
            await call(
                uid,
                "UPDATE assessment_blueprints SET label = 'x' WHERE id = :b",
                {"b": w.blueprint_id},
                role=role,
            )
            await call(
                uid,
                "DELETE FROM assessment_blueprints WHERE id = :b",
                {"b": w.blueprint_id},
                role=role,
            )
        except DBAPIError:
            pass
    assert (
        mig.scalar("SELECT label FROM assessment_blueprints WHERE id = :b", b=w.blueprint_id)
        == "RT role"
    )


# ============================================================================== RLS


async def test_other_developers_clients_and_guests_cannot_read_role_attempts_or_evidence(
    mig: Mig,
) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer_all()
    sql_attempt = "SELECT count(*) AS n FROM test_attempts WHERE id = :a"
    sql_evidence = "SELECT count(*) AS n FROM skill_evidence WHERE attempt_id = :a"
    params = {"a": run.aid}
    admin = await make_user("ADMIN")
    for sql in (sql_attempt, sql_evidence):
        assert (await call(run.user, sql, params))[0]["n"] == 1
        assert (await call(admin, sql, params, role="ADMIN"))[0]["n"] == 1
        assert (await call(await make_user(), sql, params))[0]["n"] == 0
        assert (await call(await make_user("CLIENT"), sql, params, role="CLIENT"))[0]["n"] == 0
        assert (await call(None, sql, params, role="GUEST"))[0]["n"] == 0
    # An unscoped read lists none of the owner's rows either.
    other = await make_user()
    rows = await call(other, "SELECT user_id FROM test_attempts")
    assert run.user not in {r["user_id"] for r in rows}


async def test_clients_cannot_call_the_attempt_functions_on_someone_elses_attempt(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    client = await make_user("CLIENT")
    await failed(run.current(user=client, role="CLIENT"), NO_DATA)
    await failed(
        call(
            client,
            "SELECT record_heartbeat(CAST(:a AS uuid), :now, :tok)",
            {"a": run.aid, "now": T0, "tok": run.tok},
            role="CLIENT",
        ),
        NO_DATA,
    )


async def test_guests_and_everyone_see_the_competency_catalogue_but_only_admins_write(
    mig: Mig,
) -> None:
    w = mig.world()
    sql = "SELECT count(*) AS n FROM competencies WHERE id = ANY(CAST(:c AS uuid[]))"
    params = {"c": [str(c) for c in w.comps]}
    assert (await call(None, sql, params, role="GUEST"))[0]["n"] == len(w.comps)
    assert (await call(await make_user(), sql, params))[0]["n"] == len(w.comps)
    assert (await call(await make_user("CLIENT"), sql, params, role="CLIENT"))[0]["n"] == len(
        w.comps
    )
    insert = (
        "INSERT INTO competencies (skill_id, code, name, description, is_core, keywords, position) "
        "VALUES (:s, 'rtforged1', 'Forged competency', '', false, ARRAY['kw'], 0)"
    )
    for uid, role in (
        (None, "GUEST"),
        (await make_user(), "DEVELOPER"),
        (await make_user("CLIENT"), "CLIENT"),
    ):
        with pytest.raises(DBAPIError, match=r"row-level security|permission denied"):
            await call(uid, insert, {"s": w.skill_id}, role=role)
    assert mig.scalar("SELECT count(*) FROM competencies WHERE code = 'rtforged1'") == 0


async def test_blueprints_are_readable_when_signed_in_but_not_to_guests(mig: Mig) -> None:
    w = mig.world()
    sql = "SELECT count(*) AS n FROM assessment_blueprints WHERE id = :b"
    params = {"b": w.blueprint_id}
    assert (await call(await make_user(), sql, params))[0]["n"] == 1
    assert (await call(await make_user("CLIENT"), sql, params, role="CLIENT"))[0]["n"] == 1
    assert (await call(None, sql, params, role="GUEST"))[0]["n"] == 0


async def test_the_web_role_cannot_insert_blueprints_or_slot_assessments(mig: Mig) -> None:
    w = mig.world()
    client = await make_user("CLIENT")
    project = await make_project(client, ProjectStatus.DRAFT)
    slot = await make_slot(client, project, w.skill_id)
    fingerprint = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    mig.fingerprints.append(fingerprint)
    blueprint_sql = (
        "INSERT INTO assessment_blueprints (algo_version, fingerprint, primary_skill_id, label, "
        "competencies, question_count, time_limit_seconds, difficulty_mix, pass_rule, status) "
        "VALUES (1, :f, :s, 'forged', '[]'::jsonb, 6, 900, '{}'::jsonb, '{}'::jsonb, 'AVAILABLE')"
    )
    slot_sql = (
        "INSERT INTO slot_assessments (slot_id, project_id, blueprint_id, requirements_hash) "
        "VALUES (:slot, :p, :b, :h)"
    )
    for uid, role in (
        (client, "CLIENT"),
        (await make_user("ADMIN"), "ADMIN"),
        (await make_user(), "DEVELOPER"),
    ):
        with pytest.raises(DBAPIError, match=r"row-level security|permission denied"):
            await call(uid, blueprint_sql, {"f": fingerprint, "s": w.skill_id}, role=role)
        with pytest.raises(DBAPIError, match=r"row-level security|permission denied"):
            await call(
                uid,
                slot_sql,
                {"slot": slot, "p": project, "b": w.blueprint_id, "h": "0" * 64},
                role=role,
            )
    assert (
        mig.scalar(
            "SELECT count(*) FROM assessment_blueprints WHERE fingerprint = :f", f=fingerprint
        )
        == 0
    )
    assert mig.scalar("SELECT count(*) FROM slot_assessments WHERE slot_id = :s", s=slot) == 0


async def test_the_web_role_cannot_write_attempts_or_evidence_directly(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer_all()
    before = run.row()
    attempts = (
        "UPDATE test_attempts SET passed = true, overall_bp = 10000, flagged = false WHERE id = :a",
        "DELETE FROM test_attempts WHERE id = :a",
    )
    evidence = (
        "UPDATE skill_evidence SET passed = true, score = 1 WHERE attempt_id = :a",
        "DELETE FROM skill_evidence WHERE attempt_id = :a",
    )
    for sql in (*attempts, *evidence):
        # Refused outright is fine; silently matching no row is fine too.
        with contextlib.suppress(DBAPIError):
            await call(run.user, sql, {"a": run.aid})
    assert run.row() == before
    assert len(run.evidence()) == 1
    forged = (
        "INSERT INTO skill_evidence (user_id, skill_id, source, score, blueprint_id, passed, "
        "valid_until, at) VALUES (:u, :s, 'ROLE_ASSESSMENT', 1, :b, true, "
        "now() + interval '1 year', now())"
    )
    with pytest.raises(DBAPIError, match=r"row-level security|permission denied"):
        await call(run.user, forged, {"u": run.user, "s": w.skill_id, "b": w.blueprint_id})


async def test_the_question_bank_is_unreadable_to_developers_clients_and_guests(mig: Mig) -> None:
    w = mig.world()
    sql = "SELECT count(*) AS n FROM question_bank WHERE id = ANY(CAST(:q AS uuid[]))"
    params = {"q": [str(q) for q in w.correct]}
    assert (await call(await make_user(), sql, params))[0]["n"] == 0
    assert (await call(await make_user("CLIENT"), sql, params, role="CLIENT"))[0]["n"] == 0
    assert (await call(None, sql, params, role="GUEST"))[0]["n"] == 0
    assert (await call(await make_user("ADMIN"), sql, params, role="ADMIN"))[0]["n"] == len(
        w.correct
    )
    # A developer in the middle of an attempt still cannot read the answers directly.
    run = await begin(mig, w)
    assert (await call(run.user, "SELECT correct_index FROM question_bank"))[:1] == []


async def test_pool_and_count_functions_return_no_question_content(mig: Mig) -> None:
    w = mig.world()
    uid = await make_user()
    pool = await call(
        uid,
        "SELECT * FROM role_question_pool(CAST(:b AS uuid), CAST('SELF_VERIFIED' AS review_level))",
        {"b": w.blueprint_id},
    )
    assert {q["question_id"] for q in pool} == {
        *w.ids,
        w.spare_easy,
        w.spare_medium,
        w.retired_easy,
    } - {w.retired_easy}
    assert set(pool[0]) == {"question_id", "competency_id", "difficulty", "times_served"}
    counts = await call(
        uid,
        "SELECT * FROM role_bank_counts(CAST(:s AS uuid[]), CAST('SELF_VERIFIED' AS review_level))",
        {"s": [str(w.skill_id)]},
    )
    assert set(counts[0]) == {"competency_id", "difficulty", "approved"}
    # Inactive competencies are invisible to the blueprint builder.
    assert not {str(c) for c in w.comps} & {str(r["competency_id"]) for r in counts}
    human = await call(
        uid,
        "SELECT * FROM role_question_pool(CAST(:b AS uuid), "
        "CAST('HUMAN_APPROVED' AS review_level))",
        {"b": w.blueprint_id},
    )
    assert human == []


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT role_score_core(CAST(:a AS uuid), now(), CAST(NULL AS terminated_reason))",
        "SELECT * FROM role_own_attempt(CAST(:a AS uuid), CAST(:t AS bytea))",
        "SELECT role_touch(CAST(:a AS uuid), now())",
        "SELECT role_token_state(CAST(:t AS bytea), ARRAY[]::bytea[], CAST(:t AS bytea))",
    ],
    ids=["role_score_core", "role_own_attempt", "role_touch", "role_token_state"],
)
async def test_internal_helpers_are_not_callable_by_the_runtime_roles(mig: Mig, sql: str) -> None:
    """Spec §10 / migration 0011: the internal helpers are for the definers only."""
    w = mig.world()
    run = await begin(mig, w)
    params = {"a": run.aid, "t": run.tok}
    with pytest.raises(DBAPIError, match="permission denied"):
        await call(run.user, sql, params)
    with pytest.raises(DBAPIError, match="permission denied"):
        await call(None, sql, params, system=True)
    assert run.row()["submitted_at"] is None


async def test_only_admins_void_and_review_attempts(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer_all()
    for uid, role in ((run.user, "DEVELOPER"), (await make_user("CLIENT"), "CLIENT")):
        await failed(
            call(
                uid,
                "SELECT * FROM void_role_attempt(CAST(:a AS uuid), 'no', :now)",
                {"a": run.aid, "now": T0},
                role=role,
            ),
            INSUFFICIENT,
        )
        await failed(
            call(
                uid,
                "SELECT mark_role_attempt_reviewed(CAST(:a AS uuid), :now)",
                {"a": run.aid, "now": T0},
                role=role,
            ),
            INSUFFICIENT,
        )
    assert run.evidence()[0]["voided_at"] is None


async def test_voiding_an_open_attempt_scores_it_as_void_and_voids_its_evidence(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    await run.answer(0)
    admin = await make_user("ADMIN")
    now = T0 + timedelta(minutes=2)
    rows = await call(
        admin,
        "SELECT * FROM void_role_attempt(CAST(:a AS uuid), 'suspected help', :now)",
        {"a": run.aid, "now": now},
        role="ADMIN",
    )
    assert rows[0]["user_id"] == run.user
    row = run.row()
    assert row["terminated_reason"] == "ADMIN_VOID"
    assert row["passed"] is False
    e = run.evidence()[0]
    assert (e["voided_at"], e["void_reason"], e["passed"]) == (now, "suspected help", False)


# ====================================================================== create_slot_assessment


async def make_project(client: uuid.UUID, status: ProjectStatus) -> uuid.UUID:
    async with open_session(DbContext(user_id=client, role="CLIENT")) as db:
        project = Project(
            client_id=client,
            title="Role assessment sample project",
            budget_paisa=1_000_000,
            deadline_days=30,
            team_size=2,
            status=status,
        )
        db.add(project)
        await db.flush()
        pid = project.id
        await db.commit()
    return pid


async def make_slot(client: uuid.UUID, project: uuid.UUID, skill: uuid.UUID) -> uuid.UUID:
    async with open_session(DbContext(user_id=client, role="CLIENT")) as db:
        slot = ProjectSlot(project_id=project, skill_id=skill, count=1)
        db.add(slot)
        await db.flush()
        sid = slot.id
        await db.commit()
    return sid


def blueprint_json(
    mig: Mig, skill: uuid.UUID, *, weights: tuple[int, ...] = (5000, 5000)
) -> dict[str, Any]:
    fingerprint = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    mig.fingerprints.append(fingerprint)
    return {
        "algo_version": 1,
        "fingerprint": fingerprint,
        "primary_skill_id": str(skill),
        "label": "RT slot role",
        "competencies": [
            {
                "competency_id": str(uuid.uuid4()),
                "code": f"rtslot{i}",
                "name": f"Slot competency {i}",
                "weight_bp": weight,
                "easy": 1,
                "medium": 1,
                "hard": 1,
                "reasons": [],
            }
            for i, weight in enumerate(weights)
        ],
        "question_count": 6,
        "time_limit_seconds": 900,
        "difficulty_mix": {"easy": 2, "medium": 2, "hard": 2},
        "pass_rule": RULE,
        "status": "AVAILABLE",
        "unavailable_reason": None,
    }


CREATE_LINK = (
    "SELECT create_slot_assessment(CAST(:p AS uuid), CAST(:s AS uuid), CAST(:bp AS jsonb), :h) AS r"
)


async def link(
    uid: uuid.UUID | None,
    project: uuid.UUID,
    slot: uuid.UUID,
    blueprint: dict[str, Any],
    *,
    role: str = "CLIENT",
    system: bool = False,
) -> uuid.UUID:
    rows = await call(
        uid,
        CREATE_LINK,
        {"p": project, "s": slot, "bp": json.dumps(blueprint), "h": "a" * 64},
        role=role,
        system=system,
    )
    return uuid.UUID(str(rows[0]["r"]))


@pytest.mark.parametrize("status", [ProjectStatus.DRAFT, ProjectStatus.BIDDING])
async def test_the_projects_client_links_a_blueprint_in_draft_or_bidding(
    mig: Mig, status: ProjectStatus
) -> None:
    client = await make_user("CLIENT")
    project = await make_project(client, status)
    skill = mig.any_skill()
    slot = await make_slot(client, project, skill)
    blueprint = blueprint_json(mig, skill)
    bid = await link(client, project, slot, blueprint)
    row = mig.run("SELECT * FROM assessment_blueprints WHERE id = :b", b=bid)[0]
    assert row["fingerprint"] == blueprint["fingerprint"]
    assert (row["question_count"], str(row["status"])) == (6, "AVAILABLE")
    slot_row = mig.run("SELECT * FROM slot_assessments WHERE slot_id = :s", s=slot)[0]
    assert (slot_row["blueprint_id"], slot_row["project_id"]) == (bid, project)
    assert slot_row["requirements_hash"] == "a" * 64


@pytest.mark.parametrize(
    "status", [ProjectStatus.FORMING, ProjectStatus.IN_PROGRESS, ProjectStatus.CANCELLED]
)
async def test_linking_is_refused_once_the_project_has_left_bidding(
    mig: Mig, status: ProjectStatus
) -> None:
    client = await make_user("CLIENT")
    project = await make_project(client, status)
    skill = mig.any_skill()
    slot = await make_slot(client, project, skill)
    blueprint = blueprint_json(mig, skill)
    await failed(link(client, project, slot, blueprint), INSUFFICIENT)
    assert mig.scalar("SELECT count(*) FROM slot_assessments WHERE slot_id = :s", s=slot) == 0


async def test_only_the_projects_client_or_system_may_link(mig: Mig) -> None:
    owner = await make_user("CLIENT")
    project = await make_project(owner, ProjectStatus.DRAFT)
    skill = mig.any_skill()
    slot = await make_slot(owner, project, skill)
    blueprint = blueprint_json(mig, skill)
    for uid, role in (
        (await make_user("CLIENT"), "CLIENT"),
        (await make_user(), "DEVELOPER"),
        (await make_user("ADMIN"), "ADMIN"),
        (None, "GUEST"),
    ):
        await failed(link(uid, project, slot, blueprint, role=role), INSUFFICIENT)
    assert mig.scalar("SELECT count(*) FROM slot_assessments WHERE slot_id = :s", s=slot) == 0
    assert (
        mig.scalar(
            "SELECT count(*) FROM assessment_blueprints WHERE fingerprint = :f",
            f=blueprint["fingerprint"],
        )
        == 0
    )
    # SYSTEM (the worker role) may, for any project state it is asked about.
    bid = await link(None, project, slot, blueprint, system=True)
    assert mig.scalar("SELECT blueprint_id FROM slot_assessments WHERE slot_id = :s", s=slot) == bid


async def test_a_slot_of_another_project_is_refused(mig: Mig) -> None:
    client = await make_user("CLIENT")
    project = await make_project(client, ProjectStatus.DRAFT)
    other_project = await make_project(client, ProjectStatus.DRAFT)
    skill = mig.any_skill()
    foreign_slot = await make_slot(client, other_project, skill)
    await failed(link(client, project, foreign_slot, blueprint_json(mig, skill)), NO_DATA)
    await failed(link(client, project, uuid.uuid4(), blueprint_json(mig, skill)), NO_DATA)


async def test_weights_that_do_not_sum_to_ten_thousand_are_refused(mig: Mig) -> None:
    client = await make_user("CLIENT")
    project = await make_project(client, ProjectStatus.DRAFT)
    skill = mig.any_skill()
    slot = await make_slot(client, project, skill)
    for weights in ((5000, 4000), (6000, 5000), ()):
        await failed(
            link(client, project, slot, blueprint_json(mig, skill, weights=weights)),
            CHECK_VIOLATION,
        )


async def test_a_blueprint_with_the_same_fingerprint_is_reused(mig: Mig) -> None:
    client = await make_user("CLIENT")
    project = await make_project(client, ProjectStatus.DRAFT)
    skill = mig.any_skill()
    first_slot = await make_slot(client, project, skill)
    second_slot = await make_slot(client, project, skill)
    blueprint = blueprint_json(mig, skill)
    one = await link(client, project, first_slot, blueprint)
    two = await link(client, project, second_slot, blueprint)
    assert one == two
    assert (
        mig.scalar(
            "SELECT count(*) FROM assessment_blueprints WHERE fingerprint = :f",
            f=blueprint["fingerprint"],
        )
        == 1
    )
    assert mig.scalar("SELECT count(*) FROM slot_assessments WHERE blueprint_id = :b", b=one) == 2
    # The same fingerprint on a different project is shared too (spec §16 case 9).
    other_project = await make_project(client, ProjectStatus.BIDDING)
    third_slot = await make_slot(client, other_project, skill)
    assert await link(client, other_project, third_slot, blueprint) == one


async def test_an_existing_slot_link_is_kept(mig: Mig) -> None:
    client = await make_user("CLIENT")
    project = await make_project(client, ProjectStatus.DRAFT)
    skill = mig.any_skill()
    slot = await make_slot(client, project, skill)
    first = await link(client, project, slot, blueprint_json(mig, skill))
    again = await link(client, project, slot, blueprint_json(mig, skill))  # a different fingerprint
    assert again == first
    assert (
        mig.scalar("SELECT blueprint_id FROM slot_assessments WHERE slot_id = :s", s=slot) == first
    )
    assert mig.scalar("SELECT count(*) FROM slot_assessments WHERE slot_id = :s", s=slot) == 1


async def test_slot_links_are_visible_to_whoever_can_see_the_project(mig: Mig) -> None:
    client = await make_user("CLIENT")
    draft = await make_project(client, ProjectStatus.DRAFT)
    bidding = await make_project(client, ProjectStatus.BIDDING)
    skill = mig.any_skill()
    draft_slot = await make_slot(client, draft, skill)
    bidding_slot = await make_slot(client, bidding, skill)
    await link(client, draft, draft_slot, blueprint_json(mig, skill))
    await link(client, bidding, bidding_slot, blueprint_json(mig, skill))
    sql = "SELECT slot_id FROM slot_assessments WHERE project_id = ANY(CAST(:p AS uuid[]))"
    params = {"p": [str(draft), str(bidding)]}
    seen_by_owner = {r["slot_id"] for r in await call(client, sql, params, role="CLIENT")}
    assert seen_by_owner == {draft_slot, bidding_slot}
    seen_by_dev = {r["slot_id"] for r in await call(await make_user(), sql, params)}
    assert seen_by_dev == {bidding_slot}  # a DRAFT project is private to its client


# ============================================================================== practice functions


async def test_the_practice_test_functions_refuse_role_attempts(mig: Mig) -> None:
    w = mig.world()
    run = await begin(mig, w)
    rows = await call(run.user, "SELECT * FROM attempt_questions(CAST(:a AS uuid))", {"a": run.aid})
    assert rows == []
    await failed(
        call(
            run.user,
            "SELECT record_test_answer(CAST(:a AS uuid), CAST(:q AS uuid), 0, :now)",
            {"a": run.aid, "q": w.ids[0], "now": T0},
        ),
        NO_DATA,
    )
    await failed(
        call(
            run.user,
            "SELECT * FROM score_test_attempt(CAST(:a AS uuid), :now)",
            {"a": run.aid, "now": T0},
        ),
        NO_DATA,
    )
    await failed(
        call(
            None,
            "SELECT * FROM score_test_attempt(CAST(:a AS uuid), :now)",
            {"a": run.aid, "now": T0},
            system=True,
        ),
        NO_DATA,
    )
    row = run.row()
    assert row["submitted_at"] is None
    assert row["answers"] == {}
    assert row["answers_locked"] == []
    assert run.evidence() == []
