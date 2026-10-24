"""Application configuration loaded from environment variables (spec §6.1).

Every variable documented in `.env.example` is declared here. In production the
settings are validated by :func:`validate_production`; startup is refused (fail
closed, spec §0.2 rule 3) if any insecure combination is found.
"""

from __future__ import annotations

import base64
import binascii
import os
import sys
from collections.abc import Mapping, Sequence
from enum import StrEnum
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.netutil import IPNetwork, parse_networks

MIN_SECRET_KEY_BYTES = 64
# The local mail catcher of the dev and demo stacks (never a real relay).
DEMO_MAIL_CAPTURE_HOST = "mailpit"
# `DEMO_STACK=1` (set only by docker-compose.demo.yml) is honoured only for these origins, so
# a real deployment cannot turn the demo's mail capture on by copying one variable.
DEMO_ORIGIN_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
# Command-line flags meaning auto-reload or debug mode (uvicorn, gunicorn).
_RELOAD_FLAGS = frozenset(
    {"--reload", "--reload-dir", "--reload-include", "--reload-exclude", "--debug"}
)
_VERBOSE_LOG_LEVELS = frozenset({"debug", "trace"})


class Environment(StrEnum):
    """Deployment environment (`DEVSYNC_ENV`)."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Typed view of the process environment. Never log an instance of this class."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=True)

    DEVSYNC_ENV: Environment = Environment.DEVELOPMENT
    SECRET_KEY: str = Field(default="", repr=False)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://devsync_app:devsync_app@postgres:5432/devsync", repr=False
    )
    WORKER_DATABASE_URL: str = Field(default="", repr=False)
    MIGRATION_DATABASE_URL: str = Field(
        default="postgresql+psycopg://devsync_migrator:devsync_migrator@postgres:5432/devsync",
        repr=False,
    )
    REDIS_URL: str = Field(default="redis://redis:6379/0", repr=False)
    PUBLIC_ORIGIN: str = "https://localhost"
    ALLOWED_HOSTS: str = "localhost"

    SESSION_ROTATE_MINUTES: int = Field(default=15, ge=1, le=60)
    SESSION_IDLE_MINUTES: int = Field(default=30, ge=5, le=240)
    SESSION_ABSOLUTE_HOURS: int = Field(default=168, ge=1, le=24 * 30)
    SESSION_COOKIE_SECURE: bool = True

    SMTP_HOST: str = "mailpit"
    SMTP_PORT: int = 1025
    SMTP_USERNAME: str = Field(default="", repr=False)
    SMTP_PASSWORD: str = Field(default="", repr=False)
    SMTP_STARTTLS: bool = False
    EMAIL_FROM: str = "DevSync <no-reply@devsync.local>"

    SMS_PROVIDER: str = "console"
    GITHUB_TOKEN: str = Field(default="", repr=False)
    CAPTCHA_HMAC_KEY: str = Field(default="", repr=False)
    # Comma-separated networks allowed to reach /api/v1/admin (empty = every network, §14.17).
    ADMIN_ALLOWED_CIDRS: str = ""
    GITHUB_WEBHOOK_SECRET: str = Field(default="", repr=False)
    JUDGE0_URL: str = "http://judge0:2358"
    JUDGE0_AUTH_TOKEN: str = Field(default="", repr=False)

    UPLOAD_DIR: str = "/data/uploads"
    MAX_UPLOAD_MB: int = Field(default=20, ge=1, le=100)
    TRUSTED_PROXY_IPS: str = "172.16.0.0/12"

    GUNICORN_WORKERS: int = Field(default=0, ge=0, le=64)  # 0 → 2×CPU+1
    GUNICORN_TIMEOUT: int = Field(default=30, ge=5, le=120)
    MAX_REQUESTS: int = Field(default=1000, ge=100)

    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=5, ge=0, le=100)
    DB_STATEMENT_TIMEOUT_MS: int = Field(default=5000, ge=100, le=60000)
    DB_JOB_STATEMENT_TIMEOUT_MS: int = Field(default=30000, ge=1000, le=600000)

    CACHE_TTL_SECONDS_DEFAULT: int = Field(default=60, ge=1, le=3600)
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    # Set only by docker-compose.demo.yml: the offline demo may use its local Mailpit (D61).
    DEMO_STACK: bool = False

    @field_validator("ADMIN_ALLOWED_CIDRS", "TRUSTED_PROXY_IPS")
    @classmethod
    def _networks_are_valid(cls, value: str) -> str:
        """A malformed network list stops startup in every environment (fail closed)."""
        parse_networks(value)
        return value

    @property
    def admin_allowed_networks(self) -> tuple[IPNetwork, ...]:
        """`ADMIN_ALLOWED_CIDRS` parsed; empty means no network restriction."""
        return parse_networks(self.ADMIN_ALLOWED_CIDRS)

    @property
    def trusted_proxy_networks(self) -> tuple[IPNetwork, ...]:
        """`TRUSTED_PROXY_IPS` parsed: peers whose `X-Forwarded-For` is believed."""
        return parse_networks(self.TRUSTED_PROXY_IPS)

    @property
    def allowed_hosts(self) -> list[str]:
        """`ALLOWED_HOSTS` as a list (comma separated in the environment)."""
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

    @property
    def is_production(self) -> bool:
        """True when running with production safety checks."""
        return self.DEVSYNC_ENV is Environment.PRODUCTION

    @property
    def docs_enabled(self) -> bool:
        """Swagger UI and the public OpenAPI file exist only in development (§10.1, §14.18)."""
        return self.DEVSYNC_ENV is Environment.DEVELOPMENT


def _secret_key_bytes(value: str) -> int:
    """Return the decoded length of a base64 secret, or 0 if it is not valid base64."""
    try:
        return len(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError):
        return 0


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def runtime_problems(argv: Sequence[str], environ: Mapping[str, str]) -> list[str]:
    """Auto-reload or debug switches on the server's command line or environment (§14.18).

    `uvicorn --reload` runs the app in a spawned child whose `sys.argv` is the parent's, so
    the flag is visible from inside the app factory as well.
    """
    problems: list[str] = []
    flags = {a.split("=", 1)[0] for a in argv}
    if flags & _RELOAD_FLAGS or "--reload" in environ.get("GUNICORN_CMD_ARGS", "").split():
        problems.append("auto-reload / --debug server flags are not allowed in production")
    if _truthy(environ.get("UVICORN_RELOAD")):
        problems.append("UVICORN_RELOAD is not allowed in production")
    for i, arg in enumerate(argv):
        level = ""
        if arg.startswith("--log-level="):
            level = arg.split("=", 1)[1]
        elif arg == "--log-level" and i + 1 < len(argv):
            level = argv[i + 1]
        if level.strip().lower() in _VERBOSE_LOG_LEVELS:
            problems.append("--log-level debug/trace is not allowed in production")
    return problems


def _mail_problems(settings: Settings) -> list[str]:
    """Mailpit is off in production (§14.18) except on the offline demo stack (D61)."""
    problems: list[str] = []
    if settings.SMS_PROVIDER == "mailpit" and settings.SMTP_HOST != DEMO_MAIL_CAPTURE_HOST:
        # The offline demo stack (`make demo-up`) delivers codes to its local Mailpit; anywhere
        # else that would hand one-time codes to a real mail relay.
        problems.append(
            "SMS_PROVIDER=mailpit is only allowed with SMTP_HOST=mailpit (the offline demo stack)"
        )
    demo_origin = (urlparse(settings.PUBLIC_ORIGIN).hostname or "") in DEMO_ORIGIN_HOSTS
    if settings.DEMO_STACK and not demo_origin:
        problems.append("DEMO_STACK is only allowed with a localhost PUBLIC_ORIGIN (offline demo)")
    mailpit = settings.SMTP_HOST.strip().lower() == DEMO_MAIL_CAPTURE_HOST
    if (mailpit or settings.SMS_PROVIDER == "mailpit") and not settings.DEMO_STACK:
        # §14.18 "Mailpit disabled": a real deployment needs a real relay. The default
        # SMTP_HOST is the dev catcher, so production has to set it explicitly.
        problems.append(
            "Mailpit (SMTP_HOST=mailpit or SMS_PROVIDER=mailpit) is only allowed on the "
            "offline demo stack (DEMO_STACK=1)"
        )
    return problems


def production_problems(
    settings: Settings,
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """List every insecure setting for production (empty list means safe).

    Kept separate from :func:`validate_production` so tests can assert on each
    individual problem and the startup message can print all of them at once.
    `argv` and `environ` default to the real process; tests pass their own.
    """
    argv = sys.argv if argv is None else argv
    environ = os.environ if environ is None else environ
    problems: list[str] = []
    if _secret_key_bytes(settings.SECRET_KEY) < MIN_SECRET_KEY_BYTES:
        problems.append("SECRET_KEY must be at least 64 random bytes, base64 encoded")
    if settings.SMS_PROVIDER == "console":
        problems.append("SMS_PROVIDER=console is only allowed in development")
    problems.extend(_mail_problems(settings))
    if settings.DEBUG:
        problems.append("DEBUG must be off in production")
    if settings.LOG_LEVEL.strip().lower() in _VERBOSE_LOG_LEVELS:
        problems.append("LOG_LEVEL=DEBUG is not allowed in production (verbose logs)")
    if urlparse(settings.PUBLIC_ORIGIN).scheme != "https":
        problems.append("PUBLIC_ORIGIN must use https")
    redis = urlparse(settings.REDIS_URL)
    if not redis.password:
        problems.append("REDIS_URL must include a password in production")
    if "*" in settings.allowed_hosts or not settings.allowed_hosts:
        problems.append("ALLOWED_HOSTS must list explicit host names (no '*')")
    if not settings.SESSION_COOKIE_SECURE:
        problems.append("SESSION_COOKIE_SECURE must be true in production")
    if not settings.CAPTCHA_HMAC_KEY:
        problems.append("CAPTCHA_HMAC_KEY must be set in production")
    if environ.get("DEVSYNC_CAPTCHA_BYPASS"):
        problems.append("CAPTCHA bypass is only allowed in the test environment")
    problems.extend(runtime_problems(argv, environ))
    return problems


class InsecureConfigurationError(RuntimeError):
    """Raised at startup when production settings are unsafe."""


def validate_production(settings: Settings) -> None:
    """Refuse to start in production when any problem exists (spec §6.1, §14.18)."""
    if not settings.is_production:
        return
    problems = production_problems(settings)
    if problems:
        message = "Refusing to start: insecure production configuration:\n" + "\n".join(
            f"  - {p}" for p in problems
        )
        raise InsecureConfigurationError(message)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings (cached; tests clear the cache via `get_settings.cache_clear()`)."""
    return Settings()
