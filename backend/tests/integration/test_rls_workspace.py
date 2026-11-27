"""Row-level security of the Phase 9 workspace tables (spec §14.15, §14.13 row 9; migration
0016; DECISIONS D142, D147, D149, D151, D166–D169, D173). Queries run directly as the web role:

- participants (the client and ACTIVE or COMPLETED members) read the workspace; former members,
  other clients and outsiders see nothing; admins read tasks, check-ins, events, risks and
  snapshots but not comments or discussion (Phase 12);
- members never see the BUDGET or AUTO_APPROVAL_SOON risks;
- only ACTIVE members write tasks and check-ins (their own); anyone in the project comments as
  themselves; nobody but SYSTEM writes events directly; `record_activity()` records as the
  caller, for participants only, for catalogue types only;
- check-ins, evidence and events are append-only even for SYSTEM; a row's project matches its
  parent; dependencies stay in one milestone; edits keep revisions only admins read;
- project files are readable by participants only (not the uploader after leaving, not admins).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from app.core.config import Environment
from app.db.context import DbContext
from app.db.session import open_session
from app.models.formation import MemberStatus, TeamMember
from app.models.profiles import FileKind, StoredFile
from app.models.projects import Milestone
from app.models.workspace import (
    ActivityEvent,
    Checkin,
    Comment,
    CommentRevision,
    CommentTarget,
    ForecastSnapshot,
    NotificationPreference,
    Risk,
    RiskSeverity,
    RiskType,
    Task,
    TaskDependency,
    TaskDifficulty,
    TaskEvidence,
    EvidenceKind,
)
from tests.helpers import stack_available
from tests.integration.test_rls_bids import as_user, make_user
from tests.integration.test_rls_formation import _sees, _world

pytestmark = pytest.mark.integration
DbErrors = (ProgrammingError, DBAPIError, IntegrityError)
NOW = datetime(2026, 11, 27, 6, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _require_stack(monkeypatch: pytest.MonkeyPatch, migrated: str) -> None:
    if not stack_available():
        pytest.skip("needs the test compose stack")
    monkeypatch.setenv("DEVSYNC_ENV", Environment.TEST.value)


async def _milestones(client: uuid.UUID, pid: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    async with as_user(client, "CLIENT") as db:
        a = Milestone(project_id=pid, name="Build", duration_days=5, share_bp=6000, position=0)
        b = Milestone(project_id=pid, name="Test", duration_days=3, share_bp=4000, position=1)
        db.add_all([a, b])
        await db.flush()
        ids = (a.id, b.id)
        await db.commit()
    return ids


def _task(pid: uuid.UUID, milestone: uuid.UUID, creator: uuid.UUID, pos: str = "V") -> Task:
    return Task(project_id=pid, milestone_id=milestone, title="Stock list API",
                estimate_hours=Decimal("8.0"), difficulty=TaskDifficulty.MEDIUM, position=pos,
                created_by=creator)  # fmt: skip


async def _workspace() -> dict[str, Any]:
    """The formation world with dev_a ACTIVE (lead), dev_b LEFT, and one row in every table."""
    w = await _world()
    m1, m2 = await _milestones(w["client"], w["pid"])
    async with open_session(DbContext.system(), job=True) as db:
        await db.execute(update(TeamMember).where(TeamMember.id == w["member_a"])
                         .values(status=MemberStatus.ACTIVE, is_lead=True))  # fmt: skip
        await db.execute(update(TeamMember).where(TeamMember.team_id == w["team"],
                                                  TeamMember.id != w["member_a"])
                         .values(status=MemberStatus.LEFT))  # fmt: skip
        task = _task(w["pid"], m1, w["dev_a"])
        db.add(task)
        await db.flush()
        checkin = Checkin(project_id=w["pid"], team_member_id=w["member_a"],
                          week_start=date(2026, 11, 23), done="Stock table", next="Filters",
                          confidence=4, on_time=True)  # fmt: skip
        comment = Comment(project_id=w["pid"], target_type=CommentTarget.TASK, target_id=task.id,
                          author_id=w["client"], body="Looks good")  # fmt: skip
        event = ActivityEvent(project_id=w["pid"], actor_id=w["dev_a"], type="task.moved",
                              entity_type="TASK", entity_id=task.id, data={})  # fmt: skip
        budget = Risk(
            project_id=w["pid"],
            type=RiskType.BUDGET,
            severity=RiskSeverity.MEDIUM,
            entity_type="PROJECT",
            title="Spending ahead of progress",
            opened_at=NOW,
        )
        stalled = Risk(project_id=w["pid"], type=RiskType.STALLED_TASK,
                       severity=RiskSeverity.LOW, entity_type="TASK", entity_id=task.id,
                       title="Stock list API stalled", opened_at=NOW)  # fmt: skip
        snap = ForecastSnapshot(
            project_id=w["pid"],
            day=date(2026, 11, 27),
            forecast={"finish_day": 25},
            impact_days=2,
            evaluated_at=NOW,
        )
        pfile = StoredFile(
            owner_id=w["dev_a"],
            kind=FileKind.PROJECT_FILE,
            project_id=w["pid"],
            storage_key=uuid.uuid4(),
            original_name="plan.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            sha256="0" * 64,
        )
        db.add_all([checkin, comment, event, budget, stalled, snap, pfile])
        await db.flush()
        ids = {"m1": m1, "m2": m2, "task": task.id, "checkin": checkin.id,
               "comment": comment.id, "event": event.id, "budget": budget.id,
               "stalled": stalled.id, "snap": snap.id, "file": pfile.id}  # fmt: skip
        await db.commit()
    return {**w, **ids}


async def test_participants_read_the_workspace_and_nobody_else() -> None:
    w = await _workspace()
    rows = ((Task, "task"), (Checkin, "checkin"), (ActivityEvent, "event"),
            (ForecastSnapshot, "snap"), (Comment, "comment"))  # fmt: skip
    for model, key in rows:
        assert await _sees(w["client"], "CLIENT", model, w[key]), model
        assert await _sees(w["dev_a"], "DEVELOPER", model, w[key]), model
        assert not await _sees(w["dev_b"], "DEVELOPER", model, w[key]), model  # LEFT
        assert not await _sees(w["outsider"], "DEVELOPER", model, w[key]), model
        assert not await _sees(w["other_client"], "CLIENT", model, w[key]), model
    for model, key in rows[:4]:
        assert await _sees(w["admin"], "ADMIN", model, w[key]), model
    assert not await _sees(w["admin"], "ADMIN", Comment, w["comment"])  # Phase 12 (D142)


async def test_a_completed_member_still_reads_but_an_invited_one_does_not() -> None:
    w = await _workspace()
    for status, visible in ((MemberStatus.COMPLETED, True), (MemberStatus.INVITED, False)):
        async with open_session(DbContext.system(), job=True) as db:
            await db.execute(update(TeamMember).where(TeamMember.id == w["member_a"])
                             .values(status=status, is_lead=False))  # fmt: skip
            await db.commit()
        assert await _sees(w["dev_a"], "DEVELOPER", Task, w["task"]) is visible, status


async def test_members_never_see_the_budget_risk() -> None:
    w = await _workspace()
    assert await _sees(w["client"], "CLIENT", Risk, w["budget"])
    assert await _sees(w["admin"], "ADMIN", Risk, w["budget"])
    assert not await _sees(w["dev_a"], "DEVELOPER", Risk, w["budget"])
    assert await _sees(w["dev_a"], "DEVELOPER", Risk, w["stalled"])
    assert not await _sees(w["outsider"], "DEVELOPER", Risk, w["stalled"])


async def test_only_active_members_write_tasks() -> None:
    w = await _workspace()
    async with as_user(w["dev_a"], "DEVELOPER") as db:
        db.add(_task(w["pid"], w["m1"], w["dev_a"], "W"))
        await db.commit()  # the ACTIVE member may
    for uid, role in ((w["client"], "CLIENT"), (w["dev_b"], "DEVELOPER"),
                      (w["outsider"], "DEVELOPER"), (w["admin"], "ADMIN")):  # fmt: skip
        async with as_user(uid, role) as db:
            db.add(_task(w["pid"], w["m1"], uid, "X"))
            with pytest.raises(DbErrors):
                await db.flush()
        async with as_user(uid, role) as db:
            result = await db.execute(
                update(Task).where(Task.id == w["task"]).values(title="Forged")
            )
            assert result.rowcount == 0, role


async def test_comments_are_written_as_yourself_by_participants_only() -> None:
    w = await _workspace()
    async with as_user(w["client"], "CLIENT") as db:
        db.add(Comment(project_id=w["pid"], target_type=CommentTarget.TASK, target_id=w["task"],
                       author_id=w["client"], body="Thanks"))  # fmt: skip
        await db.commit()
    forged = ((w["client"], "CLIENT", w["dev_a"]), (w["outsider"], "DEVELOPER", w["outsider"]))
    for uid, role, author in forged:
        async with as_user(uid, role) as db:
            db.add(Comment(project_id=w["pid"], target_type=CommentTarget.TASK,
                           target_id=w["task"], author_id=author, body="Forged"))  # fmt: skip
            with pytest.raises(DbErrors):
                await db.flush()
    async with as_user(w["dev_a"], "DEVELOPER") as db:  # not the author: the row is hidden
        result = await db.execute(update(Comment).where(Comment.id == w["comment"])
                                  .values(body="Edited by someone else"))  # fmt: skip
        assert result.rowcount == 0


async def test_an_edit_keeps_a_revision_only_admins_read() -> None:
    w = await _workspace()
    async with as_user(w["client"], "CLIENT") as db:
        await db.execute(update(Comment).where(Comment.id == w["comment"])
                         .values(body="Looks good now", edited_at=NOW))  # fmt: skip
        await db.commit()
    rev = select(CommentRevision.body).where(CommentRevision.comment_id == w["comment"])
    async with as_user(w["admin"], "ADMIN") as db:
        assert list(await db.scalars(rev)) == ["Looks good"]
    for uid, role in ((w["client"], "CLIENT"), (w["dev_a"], "DEVELOPER")):
        async with as_user(uid, role) as db:
            assert list(await db.scalars(rev)) == []
    async with as_user(w["client"], "CLIENT") as db:  # who and where never change
        with pytest.raises(DbErrors):
            await db.execute(update(Comment).where(Comment.id == w["comment"])
                             .values(target_id=w["m1"]))  # fmt: skip


async def test_checkins_are_your_own_and_immutable() -> None:
    w = await _workspace()
    other_member = await _other_member(w)
    async with as_user(w["dev_a"], "DEVELOPER") as db:
        db.add(Checkin(project_id=w["pid"], team_member_id=other_member,
                       week_start=date(2026, 11, 30), done="x", next="y", confidence=3,
                       on_time=True))  # fmt: skip
        with pytest.raises(DbErrors):  # someone else's member row
            await db.flush()
    for stmt in (update(Checkin).where(Checkin.id == w["checkin"]).values(done="Rewritten"),
                 delete(Checkin).where(Checkin.id == w["checkin"])):  # fmt: skip
        async with open_session(DbContext.system(), job=True) as db:
            with pytest.raises(DbErrors):
                await db.execute(stmt)


async def _other_member(w: dict[str, Any]) -> uuid.UUID:
    async with open_session(DbContext.system(), job=True) as db:
        found = await db.scalar(
            select(TeamMember.id).where(
                TeamMember.team_id == w["team"], TeamMember.id != w["member_a"]
            )
        )
    assert found is not None
    return found


async def test_events_are_append_only_and_never_written_directly_by_the_web() -> None:
    w = await _workspace()
    async with as_user(w["dev_a"], "DEVELOPER") as db:
        db.add(ActivityEvent(project_id=w["pid"], actor_id=w["dev_a"], type="task.done",
                             entity_type="TASK", entity_id=w["task"], data={}))  # fmt: skip
        with pytest.raises(DbErrors):
            await db.flush()
    for stmt in (update(ActivityEvent).where(ActivityEvent.id == w["event"]).values(data={"x": 1}),
                 delete(ActivityEvent).where(ActivityEvent.id == w["event"])):  # fmt: skip
        async with open_session(DbContext.system(), job=True) as db:
            with pytest.raises(DbErrors):
                await db.execute(stmt)


RECORD = text(
    "SELECT record_activity(:p, :t, 'TASK', :e, :s, CAST(:d AS jsonb), CAST(:at AS timestamptz))"
)


async def test_record_activity_records_the_caller_for_participants_only() -> None:
    w = await _workspace()
    args = {"p": w["pid"], "t": "task.done", "e": w["task"], "s": None, "d": "{}", "at": NOW}
    async with as_user(w["dev_a"], "DEVELOPER") as db:
        event_id = await db.scalar(RECORD, args)
        await db.commit()
    async with open_session(DbContext.system(), job=True) as db:
        row = await db.get(ActivityEvent, event_id)
        assert row is not None and row.actor_id == w["dev_a"] and row.at == NOW
    refused = [
        (w["outsider"], "DEVELOPER", args),
        (w["dev_b"], "DEVELOPER", args),  # former member
        (w["admin"], "ADMIN", args),  # not a participant (admin decisions run as SYSTEM)
        (w["dev_a"], "DEVELOPER", {**args, "t": "task.forged"}),
        (w["dev_a"], "DEVELOPER", {**args, "s": w["outsider"]}),  # subject outside the project
    ]
    for uid, role, bad in refused:
        async with as_user(uid, role) as db:
            with pytest.raises(DbErrors):
                await db.scalar(RECORD, bad)


async def test_a_rows_project_matches_its_parent() -> None:
    w = await _workspace()
    other_pid = await _other_project()
    async with open_session(DbContext.system(), job=True) as db:
        db.add(_task(other_pid, w["m1"], w["dev_a"]))  # milestone of another project
        with pytest.raises(DbErrors):
            await db.flush()
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(update(Task).where(Task.id == w["task"]).values(project_id=other_pid))


async def _other_project() -> uuid.UUID:
    from tests.integration.test_rls_bids import make_bidding_project

    client = await make_user("CLIENT")
    pid, _ = await make_bidding_project(client)
    return pid


async def test_dependencies_stay_inside_one_milestone() -> None:
    w = await _workspace()
    async with open_session(DbContext.system(), job=True) as db:
        same = _task(w["pid"], w["m1"], w["dev_a"], "W")
        other = _task(w["pid"], w["m2"], w["dev_a"], "W")
        db.add_all([same, other])
        await db.flush()
        db.add(TaskDependency(project_id=w["pid"], task_id=same.id, depends_on_task_id=w["task"]))
        await db.flush()  # same milestone: fine
        db.add(TaskDependency(project_id=w["pid"], task_id=other.id, depends_on_task_id=w["task"]))
        with pytest.raises(DbErrors):
            await db.flush()


async def test_evidence_needs_a_live_project_file_and_blocks_task_deletion() -> None:
    w = await _workspace()
    async with open_session(DbContext.system(), job=True) as db:
        portfolio = StoredFile(
            owner_id=w["dev_a"],
            kind=FileKind.PORTFOLIO_IMAGE,
            storage_key=uuid.uuid4(),
            original_name="me.png",
            mime_type="image/png",
            size_bytes=10,
            sha256="1" * 64,
        )
        db.add(portfolio)
        await db.flush()
        db.add(TaskEvidence(project_id=w["pid"], task_id=w["task"], kind=EvidenceKind.FILE,
                            file_id=portfolio.id, added_by=w["dev_a"]))  # fmt: skip
        with pytest.raises(DbErrors):  # not a project file
            await db.flush()
    async with open_session(DbContext.system(), job=True) as db:
        db.add(TaskEvidence(project_id=w["pid"], task_id=w["task"], kind=EvidenceKind.SCREENSHOT,
                            file_id=w["file"], added_by=w["dev_a"]))  # fmt: skip
        with pytest.raises(DbErrors):  # a PDF isn't a screenshot (D168)
            await db.flush()
    async with as_user(w["dev_a"], "DEVELOPER") as db:
        db.add(TaskEvidence(project_id=w["pid"], task_id=w["task"], kind=EvidenceKind.PR,
                            url="https://github.com/acme/inventory/pull/12",
                            added_by=w["dev_a"]))  # fmt: skip
        await db.commit()
    async with as_user(w["dev_a"], "DEVELOPER") as db:
        with pytest.raises(DbErrors):  # evidence is kept, so its task stays (D173)
            await db.execute(delete(Task).where(Task.id == w["task"]))
    bad_urls = ("http://github.com/a/b/pull/1", "https://gitlab.com/a/b/pull/1")
    for url in bad_urls:
        async with as_user(w["dev_a"], "DEVELOPER") as db:
            db.add(TaskEvidence(project_id=w["pid"], task_id=w["task"], kind=EvidenceKind.PR,
                                url=url, added_by=w["dev_a"]))  # fmt: skip
            with pytest.raises(DbErrors):
                await db.flush()


FILE_ACCESS = text("SELECT count(*) FROM file_access(:f)")


async def test_project_files_are_for_participants_only() -> None:
    w = await _workspace()
    readers = ((w["client"], "CLIENT", 1), (w["dev_a"], "DEVELOPER", 1),
               (w["outsider"], "DEVELOPER", 0), (w["other_client"], "CLIENT", 0),
               (w["admin"], "ADMIN", 0))  # fmt: skip
    for uid, role, expected in readers:
        async with as_user(uid, role) as db:
            assert await db.scalar(FILE_ACCESS, {"f": w["file"]}) == expected, role
    async with open_session(DbContext.system(), job=True) as db:  # the uploader leaves
        await db.execute(update(TeamMember).where(TeamMember.id == w["member_a"])
                         .values(status=MemberStatus.LEFT, is_lead=False))  # fmt: skip
        await db.commit()
    async with as_user(w["dev_a"], "DEVELOPER") as db:
        assert await db.scalar(FILE_ACCESS, {"f": w["file"]}) == 0


async def test_a_project_file_needs_a_project_and_never_moves() -> None:
    w = await _workspace()
    async with open_session(DbContext.system(), job=True) as db:
        db.add(StoredFile(owner_id=w["dev_a"], kind=FileKind.PROJECT_FILE,
                          storage_key=uuid.uuid4(), original_name="x.txt", mime_type="text/plain",
                          size_bytes=1, sha256="2" * 64))  # fmt: skip
        with pytest.raises(DbErrors):
            await db.flush()
    other_pid = await _other_project()
    async with open_session(DbContext.system(), job=True) as db:
        with pytest.raises(DbErrors):
            await db.execute(update(StoredFile).where(StoredFile.id == w["file"])
                             .values(project_id=other_pid))  # fmt: skip


async def test_preferences_are_your_own() -> None:
    w = await _workspace()
    async with as_user(w["dev_a"], "DEVELOPER") as db:
        db.add(NotificationPreference(user_id=w["dev_a"], type="mentions", in_app=True, email=True))
        await db.commit()
    async with as_user(w["client"], "CLIENT") as db:
        rows = select(NotificationPreference.id).where(NotificationPreference.user_id == w["dev_a"])
        assert await db.scalar(rows) is None
        db.add(NotificationPreference(user_id=w["dev_a"], type="team", in_app=False, email=False))
        with pytest.raises(DbErrors):
            await db.flush()
