"""Queueing a background task by name (`app/core/task_queue.py`, spec §11, §15.2).

Only the tasks listed in `TASKS` can be queued; each entry must name a real job function and
carry the §11 limits it is queued with. Redis is not touched: `Queue` is replaced by a recorder.
"""

from __future__ import annotations

import importlib
from typing import Any, ClassVar

import pytest

from app.core import task_queue
from app.core.task_queue import TASKS, TaskSpec
from app.jobs.queues import QUEUE_NAMES

pytestmark = pytest.mark.unit


class _Job:
    id = "job-123"


class _RecordingQueue:
    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, name: str, connection: Any) -> None:
        self.name = name
        self.connection = connection

    def enqueue(self, path: str, *args: str, **kwargs: Any) -> _Job:
        _RecordingQueue.calls.append({"queue": self.name, "path": path, "args": args, **kwargs})
        return _Job()


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    _RecordingQueue.calls = []
    monkeypatch.setattr(task_queue, "Queue", _RecordingQueue)
    monkeypatch.setattr(task_queue, "sync_redis", lambda: "redis-connection")
    return _RecordingQueue.calls


@pytest.mark.parametrize("name", sorted(TASKS))
def test_every_task_names_a_real_job_function(name: str) -> None:
    module_path, _, func = TASKS[name].path.rpartition(".")
    assert module_path.startswith("app.jobs.")  # services never import app.jobs (layering)
    assert callable(getattr(importlib.import_module(module_path), func))


@pytest.mark.parametrize("name", sorted(TASKS))
def test_every_task_has_sane_limits(name: str) -> None:
    spec = TASKS[name]
    assert spec.queue in QUEUE_NAMES  # a queue the worker listens on
    assert 0 < spec.timeout <= 600
    assert 0 <= spec.retries <= 3


def test_the_formation_run_is_urgent_and_never_retried() -> None:
    """A run streams progress to a waiting client (high queue, 60 s); a retry would start a
    second optimisation over the same run row, so it gets none."""
    assert TASKS["formation.run"] == TaskSpec(
        "app.jobs.formation_jobs.formation_run", "high", 60, 0
    )


def test_enqueue_passes_the_spec_to_rq(recorder: list[dict[str, Any]]) -> None:
    job_id = task_queue.enqueue("formation.run", "run-1")
    assert job_id == "job-123"
    (call,) = recorder
    assert call["queue"] == "high"
    assert call["path"] == "app.jobs.formation_jobs.formation_run"
    assert call["args"] == ("run-1",)
    assert call["job_timeout"] == 60
    assert call["result_ttl"] == 3600
    assert call["retry"] is None  # retries = 0: no Retry object at all


def test_enqueue_with_retries_sets_an_rq_retry(recorder: list[dict[str, Any]]) -> None:
    task_queue.enqueue("formation.explanations", "run-2")
    (call,) = recorder
    assert call["queue"] == "default"
    assert call["job_timeout"] == 120
    assert call["retry"] is not None
    assert call["retry"].max == 1


def test_enqueue_passes_several_arguments_in_order(recorder: list[dict[str, Any]]) -> None:
    task_queue.enqueue("formation.verify", "run-3", "job-9")
    assert recorder[0]["args"] == ("run-3", "job-9")


@pytest.mark.parametrize(
    "name", ["", "formation", "formation.run ", "app.jobs.formation_jobs.formation_run"]
)
def test_an_unlisted_name_is_refused_before_anything_is_queued(
    recorder: list[dict[str, Any]], name: str
) -> None:
    """Only listed tasks can be queued: a dotted path or a near-miss name is not one."""
    with pytest.raises(KeyError):
        task_queue.enqueue(name, "run-1")
    assert recorder == []
