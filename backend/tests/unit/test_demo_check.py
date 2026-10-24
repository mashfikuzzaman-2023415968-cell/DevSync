"""Demo readiness report helpers (spec §17.0): the gate line states the recorded result, the
video is the first chromium run's, and the gallery escapes captions and runs no scripts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import demo_check
from scripts.demo_check import first_video, gate_lines, load_steps

pytestmark = pytest.mark.unit

GATE = {
    "phase": 5,
    "result": "FAIL",
    "failed_step": 7,
    "finished_at": "2026-10-24T05:03:15+00:00",
    "offline": False,
    "steps": [
        {"number": 1, "name": "Environment", "status": "PASS", "seconds": 1.2, "notes": "ok"},
        {"number": 7, "name": "Dependency audit", "status": "FAIL", "seconds": 17,
         "notes": "a | b\n" + "x" * 1000},
    ],
}  # fmt: skip


def test_gate_line_reports_the_recorded_failure_and_step() -> None:
    lines = gate_lines(5, GATE, ran_ok=False)
    assert lines[0].startswith("- Phase gate (through phase 5): **FAIL** at step 7")
    table = [line for line in lines if line.startswith("| 7 ")]
    assert table
    assert "a \\| b x" in table[0]  # pipes escaped, newlines flattened
    assert len(table[0]) < 400  # long tool logs are cut


def test_gate_line_flags_a_mismatch_with_this_run() -> None:
    lines = gate_lines(5, {**GATE, "result": "PASS"}, ran_ok=False)
    assert "**PASS**" in lines[0]
    assert any("does not match" in line for line in lines)


@pytest.mark.parametrize(("ran", "word"), [(None, "not run"), (True, "PASS"), (False, "FAIL")])
def test_gate_line_without_a_gate_file(ran: bool | None, word: str) -> None:
    assert f"**{word}**" in gate_lines(5, None, ran)[0]


def test_first_video_is_desktop_chromium_first_repeat(tmp_path: Path) -> None:
    for name in (
        "demos-demo-1-Demo-1-x-chromium-repeat1",
        "demos-demo-1-Demo-1-x-chromium",
        "demos-demo-1-Demo-1-x-chromium-gpu",
        "demos-demo-1-Demo-1-x-mobile",
        "phase5-other-chromium",
    ):
        (tmp_path / name).mkdir()
        (tmp_path / name / "video.webm").write_text(name)
    found = first_video(tmp_path, 1)
    assert found is not None
    assert found.parent.name == "demos-demo-1-Demo-1-x-chromium"
    assert first_video(tmp_path, 2) is None


def test_steps_load_and_missing_folder_is_empty(tmp_path: Path) -> None:
    run = tmp_path / "chromium" / "r0"
    run.mkdir(parents=True)
    (run / "steps.json").write_text(
        json.dumps([{"file": "01-a.png", "dark": None, "caption": "A"}])
    )
    steps = load_steps(tmp_path, "chromium")
    assert [(s.file, s.dark, s.caption) for s in steps] == [("01-a.png", None, "A")]
    assert load_steps(tmp_path, "mobile") == []


def test_gallery_escapes_captions_and_has_no_scripts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo_check, "DEMOS", tmp_path)
    run = tmp_path / "demo-1" / "chromium" / "r0"
    run.mkdir(parents=True)
    (run / "steps.json").write_text(
        json.dumps([{"file": "01-a.png", "dark": "01-a-dark.png", "caption": "<b>x</b>"}])
    )
    page = demo_check.write_gallery(1).read_text()
    assert "&lt;b&gt;x&lt;/b&gt;" in page
    assert "<script" not in page
    assert 'src="demo-1/chromium/r0/01-a-dark.png"' in page
    assert page.count("not captured") == 2  # no mobile run
