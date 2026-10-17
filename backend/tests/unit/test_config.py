"""Config defaults, overrides and production startup validation (spec §6.1, §14.18)."""

from __future__ import annotations

import base64
import secrets

import pytest

from app.core.config import (
    Environment,
    InsecureConfigurationError,
    Settings,
    production_problems,
    validate_production,
)

pytestmark = pytest.mark.unit

STRONG_KEY = base64.b64encode(secrets.token_bytes(64)).decode()


def secure_production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DEVSYNC_ENV": Environment.PRODUCTION,
        "SECRET_KEY": STRONG_KEY,
        "SMS_PROVIDER": "twilio",
        "PUBLIC_ORIGIN": "https://devsync.example",
        "REDIS_URL": "redis://:pw@redis:6379/0",
        "ALLOWED_HOSTS": "devsync.example",
        "CAPTCHA_HMAC_KEY": "k" * 32,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every settings variable from the environment so defaults are really tested."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.usefixtures("clean_env")
def test_defaults_are_development_values() -> None:
    s = Settings()
    assert s.DEVSYNC_ENV is Environment.DEVELOPMENT
    assert s.SESSION_ROTATE_MINUTES == 15
    assert s.SESSION_IDLE_MINUTES == 30
    assert s.SESSION_ABSOLUTE_HOURS == 168
    assert s.MAX_UPLOAD_MB == 20
    assert s.DB_STATEMENT_TIMEOUT_MS == 5000
    assert s.docs_enabled is True


def test_env_overrides_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOWED_HOSTS", "a.example, b.example")
    monkeypatch.setenv("MAX_UPLOAD_MB", "5")
    s = Settings()
    assert s.allowed_hosts == ["a.example", "b.example"]
    assert s.MAX_UPLOAD_MB == 5


@pytest.mark.parametrize("value", ["0", "101"])
def test_out_of_range_values_are_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", value)
    with pytest.raises(ValueError, match="MAX_UPLOAD_MB"):
        Settings()


def test_secure_production_config_passes() -> None:
    s = secure_production()
    assert production_problems(s) == []
    validate_production(s)


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"SECRET_KEY": ""}, "SECRET_KEY"),
        ({"SECRET_KEY": base64.b64encode(b"x" * 63).decode()}, "SECRET_KEY"),
        ({"SECRET_KEY": "not base64 !!"}, "SECRET_KEY"),
        ({"SMS_PROVIDER": "console"}, "SMS_PROVIDER"),
        ({"DEBUG": True}, "DEBUG"),
        ({"PUBLIC_ORIGIN": "http://devsync.example"}, "https"),
        ({"REDIS_URL": "redis://redis:6379/0"}, "REDIS_URL"),
        ({"ALLOWED_HOSTS": "*"}, "ALLOWED_HOSTS"),
        ({"ALLOWED_HOSTS": ""}, "ALLOWED_HOSTS"),
        ({"SESSION_COOKIE_SECURE": False}, "SESSION_COOKIE_SECURE"),
        ({"CAPTCHA_HMAC_KEY": ""}, "CAPTCHA_HMAC_KEY"),
    ],
)
def test_each_insecure_production_combo_is_refused(
    override: dict[str, object], fragment: str
) -> None:
    s = secure_production(**override)
    problems = production_problems(s)
    assert any(fragment in p for p in problems), problems
    with pytest.raises(InsecureConfigurationError, match=fragment):
        validate_production(s)


def test_captcha_bypass_refused_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEVSYNC_CAPTCHA_BYPASS", "1")
    assert any("CAPTCHA bypass" in p for p in production_problems(secure_production()))


def test_all_problems_are_reported_together() -> None:
    s = secure_production(SECRET_KEY="", DEBUG=True, SMS_PROVIDER="console")
    with pytest.raises(InsecureConfigurationError) as exc:
        validate_production(s)
    text = str(exc.value)
    assert "SECRET_KEY" in text
    assert "DEBUG" in text
    assert "SMS_PROVIDER" in text


@pytest.mark.usefixtures("clean_env")
def test_validation_is_skipped_outside_production() -> None:
    validate_production(Settings(DEVSYNC_ENV=Environment.DEVELOPMENT, SECRET_KEY=""))


def test_secrets_are_hidden_from_repr() -> None:
    s = secure_production()
    assert STRONG_KEY not in repr(s)
    assert "pw@" not in repr(s)
