"""Production startup refusal: Mailpit, auto-reload/debug, test router, network lists (§14.18)."""

from __future__ import annotations

import base64
import secrets

import pytest
from fastapi import APIRouter, FastAPI

from app.core.config import (
    Environment,
    InsecureConfigurationError,
    Settings,
    production_problems,
    runtime_problems,
)
from app.main import assert_no_test_routes, create_app
from tests.conftest import make_settings

pytestmark = pytest.mark.unit

PROD_ARGV = ["gunicorn", "-c", "gunicorn.conf.py", "app.main:app_factory()"]


def production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "DEVSYNC_ENV": Environment.PRODUCTION,
        "SECRET_KEY": base64.b64encode(secrets.token_bytes(64)).decode(),
        "SMS_PROVIDER": "twilio",
        "SMTP_HOST": "smtp.devsync.example",
        "PUBLIC_ORIGIN": "https://devsync.example",
        "REDIS_URL": "redis://:pw@redis:6379/0",
        "ALLOWED_HOSTS": "devsync.example",
        "CAPTCHA_HMAC_KEY": "k" * 32,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def demo(**overrides: object) -> Settings:
    """docker-compose.demo.yml: production settings plus the local Mailpit."""
    values: dict[str, object] = {
        "SMS_PROVIDER": "mailpit",
        "SMTP_HOST": "mailpit",
        "DEMO_STACK": True,
        "PUBLIC_ORIGIN": "https://localhost",
        "ALLOWED_HOSTS": "localhost,api",
    }
    values.update(overrides)
    return production(**values)


def problems(s: Settings, argv: list[str] | None = None, env: dict[str, str] | None = None) -> str:
    return "\n".join(production_problems(s, argv=argv or PROD_ARGV, environ=env or {}))


# ------------------------------------------------------------------ Mailpit (§14.18, D61)


def test_real_production_and_the_demo_stack_both_pass() -> None:
    assert problems(production()) == ""
    assert problems(demo()) == ""


@pytest.mark.parametrize("host", ["mailpit", "MAILPIT", " mailpit "])
def test_mailpit_smtp_is_refused_in_real_production(host: str) -> None:
    assert "Mailpit" in problems(production(SMTP_HOST=host))


def test_default_smtp_host_is_mailpit_so_production_must_set_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    s = Settings(**{k: v for k, v in production().model_dump().items() if k != "SMTP_HOST"})
    assert s.SMTP_HOST == "mailpit"
    assert "Mailpit" in problems(s)


def test_mailpit_sms_without_the_demo_flag_is_refused() -> None:
    assert "Mailpit" in problems(demo(DEMO_STACK=False))


@pytest.mark.parametrize(
    "origin", ["https://devsync.example", "https://localhost.devsync.example", "https://10.0.0.5"]
)
def test_demo_flag_only_counts_on_a_localhost_origin(origin: str) -> None:
    assert "DEMO_STACK" in problems(demo(PUBLIC_ORIGIN=origin, ALLOWED_HOSTS="devsync.example"))


@pytest.mark.parametrize("origin", ["https://127.0.0.1", "https://[::1]", "https://localhost:8443"])
def test_demo_flag_accepts_loopback_origins(origin: str) -> None:
    assert "DEMO_STACK" not in problems(demo(PUBLIC_ORIGIN=origin))


# ------------------------------------------------------------- auto-reload / debug (§14.18)


@pytest.mark.parametrize(
    "argv",
    [
        ["uvicorn", "app.main:app_factory", "--factory", "--reload"],
        ["uvicorn", "app.main:app_factory", "--reload-dir", "/app/app"],
        ["uvicorn", "app.main:app_factory", "--reload-dir=/app/app"],
        ["gunicorn", "--reload", "app.main:app_factory()"],
        ["gunicorn", "--debug", "app.main:app_factory()"],
    ],
)
def test_reload_or_debug_flags_are_refused(argv: list[str]) -> None:
    assert "auto-reload" in problems(production(), argv=argv)


@pytest.mark.parametrize(
    "env",
    [{"GUNICORN_CMD_ARGS": "--workers 2 --reload"}, {"UVICORN_RELOAD": "true"}],
)
def test_reload_switched_on_by_environment_is_refused(env: dict[str, str]) -> None:
    assert "reload" in problems(production(), env=env).lower()


@pytest.mark.parametrize(
    "argv",
    [
        ["uvicorn", "app.main:app_factory", "--log-level", "debug"],
        ["uvicorn", "app.main:app_factory", "--log-level=TRACE"],
    ],
)
def test_verbose_server_log_level_is_refused(argv: list[str]) -> None:
    assert "--log-level" in problems(production(), argv=argv)


def test_debug_log_level_setting_is_refused() -> None:
    assert "LOG_LEVEL" in problems(production(LOG_LEVEL="debug"))


def test_harmless_flags_are_not_mistaken_for_reload() -> None:
    argv = ["gunicorn", "--reloader-not-a-flag", "--log-level", "info", "app.main:app_factory()"]
    assert runtime_problems(argv, {"UVICORN_RELOAD": "0", "GUNICORN_CMD_ARGS": ""}) == []


def test_create_app_refuses_reload_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["uvicorn", "app.main:app_factory", "--reload"])
    with pytest.raises(InsecureConfigurationError, match="auto-reload"):
        create_app(production(ALLOWED_HOSTS="testserver"))


# ------------------------------------------------------------------ test router (§14.18)


def _app_with_test_route() -> FastAPI:
    app = FastAPI()
    router = APIRouter(prefix="/__test__")
    router.add_api_route("/seed", lambda: None)
    app.include_router(router, prefix="/api/v1")
    return app


@pytest.mark.parametrize("env", [Environment.DEVELOPMENT, Environment.PRODUCTION])
def test_test_routes_outside_the_test_environment_stop_startup(env: Environment) -> None:
    with pytest.raises(InsecureConfigurationError, match="test-only routes"):
        assert_no_test_routes(_app_with_test_route(), make_settings(DEVSYNC_ENV=env))


def test_test_routes_are_allowed_only_in_test() -> None:
    assert_no_test_routes(_app_with_test_route(), make_settings())


def test_test_seed_endpoints_are_caught_even_under_another_prefix() -> None:
    from app.api.v1 import test_seed  # noqa: PLC0415

    app = FastAPI()
    app.include_router(test_seed.router, prefix="/innocent")
    with pytest.raises(InsecureConfigurationError, match="test-only routes"):
        assert_no_test_routes(app, make_settings(DEVSYNC_ENV=Environment.DEVELOPMENT))


def test_development_app_has_no_test_routes() -> None:
    app = create_app(make_settings(DEVSYNC_ENV=Environment.DEVELOPMENT))
    assert_no_test_routes(app, make_settings(DEVSYNC_ENV=Environment.PRODUCTION))


# ------------------------------------------------- network lists are validated (fail closed)


@pytest.mark.parametrize(
    "value",
    ["10.0.0.0/33", "10.0.0.1/8", "not-an-ip", "*", "10.0.0.0/8;192.0.2.0/24", "2001:db8::/129"],
)
@pytest.mark.parametrize("name", ["ADMIN_ALLOWED_CIDRS", "TRUSTED_PROXY_IPS"])
def test_malformed_network_lists_stop_startup(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        make_settings(**{name: value})


def test_network_lists_parse_ipv4_ipv6_and_single_hosts() -> None:
    s = make_settings(ADMIN_ALLOWED_CIDRS=" 10.0.0.0/8, 2001:db8::/32 ,192.0.2.7,")
    assert [str(n) for n in s.admin_allowed_networks] == [
        "10.0.0.0/8",
        "2001:db8::/32",
        "192.0.2.7/32",
    ]
    assert make_settings(ADMIN_ALLOWED_CIDRS="").admin_allowed_networks == ()
