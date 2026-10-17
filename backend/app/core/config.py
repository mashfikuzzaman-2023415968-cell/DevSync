"""Application configuration loaded from environment variables (spec §6.1).

Every variable documented in `.env.example` is declared here. In production the
settings are validated by :func:`validate_production`; startup is refused (fail
closed, spec §0.2 rule 3) if any insecure combination is found.
"""

from __future__ import annotations

import base64
import binascii
import os
from enum import StrEnum
from functools import lru_cache
from urllib.parse import urlparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_KEY_BYTES = 64


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


def production_problems(settings: Settings) -> list[str]:
    """List every insecure setting for production (empty list means safe).

    Kept separate from :func:`validate_production` so tests can assert on each
    individual problem and the startup message can print all of them at once.
    """
    problems: list[str] = []
    if _secret_key_bytes(settings.SECRET_KEY) < MIN_SECRET_KEY_BYTES:
        problems.append("SECRET_KEY must be at least 64 random bytes, base64 encoded")
    if settings.SMS_PROVIDER == "console":
        problems.append("SMS_PROVIDER=console is only allowed in development")
    if settings.DEBUG:
        problems.append("DEBUG must be off in production")
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
    if os.environ.get("DEVSYNC_CAPTCHA_BYPASS"):
        problems.append("CAPTCHA bypass is only allowed in the test environment")
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
