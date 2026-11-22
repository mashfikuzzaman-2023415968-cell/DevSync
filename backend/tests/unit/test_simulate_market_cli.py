"""The simulator CLI: deterministic files, bounded size, invalid input refused."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.simulate_market import main

pytestmark = pytest.mark.unit


def test_same_arguments_write_identical_files(tmp_path: Path) -> None:
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    assert main(["--seed", "3", "--developers", "10", "--out", str(a)]) == 0
    assert main(["--seed", "3", "--developers", "10", "--out", str(b)]) == 0
    assert a.read_bytes() == b.read_bytes()
    data = json.loads(a.read_text(encoding="utf-8"))
    assert data["seed"] == 3
    assert len(data["developers"]) == 10


def test_writes_to_standard_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--seed", "3", "--developers", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["seed"] == 3


@pytest.mark.parametrize(
    "args",
    [["--developers", "-1"], ["--developers", "5001"], ["--clients", "0"],
     ["--newcomer-share", "1.5"], ["--seed", "x"]],
)  # fmt: skip
def test_invalid_arguments_are_refused(args: list[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
