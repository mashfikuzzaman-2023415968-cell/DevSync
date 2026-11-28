"""The DAST scan's own rules (D157, D177): the session never survives in ZAP's output or the
reports; High and Medium alerts fail, Low and Informational don't; an ignore entry needs a real
DECISIONS entry (a missing or made-up one stops the scan); the plan carries the session only in
the replacer, excludes the test router, sign-out and the streams, and checks it is signed in."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import zap_scan

pytestmark = pytest.mark.unit
COOKIE = "__Host-ds_csrf=abc.def; __Host-ds_session=s3cr3t-value"


def _report(tmp_path: Path, *alerts: tuple[str, str]) -> Path:
    path = tmp_path / "report.json"
    data = {
        "site": [
            {
                "@name": "https://localhost:8443",
                "alerts": [
                    {
                        "pluginid": pid,
                        "riskcode": risk,
                        "name": f"alert {pid}",
                        "instances": [{"uri": "https://localhost:8443/x", "method": "GET"}],
                    }
                    for pid, risk in alerts
                ],
            }
        ]
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_the_session_is_redacted_wherever_it_appears() -> None:
    text = f"Job replacer set replacementString = {COOKIE}\nCookie: __Host-ds_session=other1"
    out = zap_scan.redact(text, COOKIE)
    assert "s3cr3t" not in out
    assert "other1" not in out
    assert "abc.def" not in out
    assert out.count("<redacted>") >= 2


def test_high_and_medium_fail_low_and_informational_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(zap_scan, "IGNORE_FILE", tmp_path / "none.json")
    ok, summary = zap_scan._verdict(_report(tmp_path, ("10015", "0"), ("10020", "1")))
    assert ok
    assert summary.startswith("High 0, Medium 0, Low 1, Informational 1")
    ok, summary = zap_scan._verdict(_report(tmp_path, ("10038", "2")))
    assert not ok
    assert "Medium 10038" in summary
    ok, _ = zap_scan._verdict(_report(tmp_path, ("40012", "3")))
    assert not ok


def test_an_ignore_entry_needs_a_real_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ignore = tmp_path / "ignore.json"
    decisions = tmp_path / "DECISIONS.md"
    decisions.write_text("**D177 · How the DAST step runs.** …\n", encoding="utf-8")
    monkeypatch.setattr(zap_scan, "IGNORE_FILE", ignore)
    monkeypatch.setattr(zap_scan, "DECISIONS", decisions)
    ignore.write_text(json.dumps([{"pluginid": "10038", "decision": "D177"}]), encoding="utf-8")
    ok, summary = zap_scan._verdict(_report(tmp_path, ("10038", "2")))
    assert ok
    assert "D177" in summary
    for bad in ("D999", "because", ""):
        ignore.write_text(json.dumps([{"pluginid": "10038", "decision": bad}]), encoding="utf-8")
        with pytest.raises(SystemExit):
            zap_scan._verdict(_report(tmp_path, ("10038", "2")))


def test_the_plan_is_signed_in_and_stays_off_dangerous_urls() -> None:
    plan = json.loads(zap_scan._plan(COOKIE, "11111111-2222-4333-8444-555555555555"))
    assert json.dumps(plan).count("s3cr3t-value") == 1  # only in the replacer rule
    replacer = next(j for j in plan["jobs"] if j["type"] == "replacer")
    assert replacer["rules"][0]["replacementString"] == COOKIE
    excluded = plan["env"]["contexts"][0]["excludePaths"]
    for path in ("__test__", "logout", "notifications/stream", "events", "files/blob"):
        assert any(path in rule for rule in excluded), path
    requests = next(j for j in plan["jobs"] if j["type"] == "requestor")["requests"]
    assert requests[0] == {
        "url": "https://localhost:8443/api/v1/me",
        "method": "GET",
        "responseCode": 200,
    }
    assert {r["method"] for r in requests} == {"GET"}
    assert {j["type"] for j in plan["jobs"]} >= {"spider", "spiderClient", "passiveScan-wait"}
    assert "activeScan" not in {j["type"] for j in plan["jobs"]}
