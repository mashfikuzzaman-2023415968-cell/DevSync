"""Structured JSON logging with request ids and secret redaction (spec §14.12, §15.7).

Rule 0.2.12: secrets (passwords, tokens, OTPs, session ids, TOTP secrets, API
keys, full phone numbers) are never logged. The redaction processor runs on
every event before rendering, so even a careless `log.info(token=...)` is safe.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Mapping, MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

REDACTED = "[REDACTED]"

# Keys whose values are always hidden (matched case-insensitively anywhere in the key).
SENSITIVE_KEY = re.compile(
    r"password|token|secret|otp|code|session|authorization|cookie|totp|phone|api[_-]?key",
    re.IGNORECASE,
)
# Values that look like secrets even under an innocent key.
BEARER_VALUE = re.compile(r"\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
LONG_TOKEN_VALUE = re.compile(r"\b[A-Za-z0-9_-]{32,}\b")
EMAIL_VALUE = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_VALUE = re.compile(r"\+?\d[\d\s-]{8,}\d")

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _redact_string(value: str) -> str:
    """Mask secret-looking substrings inside a free-text value."""
    value = BEARER_VALUE.sub(lambda m: f"{m.group(1)} {REDACTED}", value)
    value = LONG_TOKEN_VALUE.sub(REDACTED, value)
    value = EMAIL_VALUE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", value)
    return PHONE_VALUE.sub(REDACTED, value)


def redact(value: Any, key: str | None = None) -> Any:
    """Return a copy of ``value`` with sensitive keys and secret-looking values masked."""
    if key is not None and SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {k: redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


# Structlog's own bookkeeping keys must not be rewritten by the redactor.
_PASSTHROUGH_KEYS = frozenset({"event", "level", "timestamp", "logger", "request_id"})


def redaction_processor(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that redacts every field except structlog's own bookkeeping."""
    for k in list(event_dict.keys()):
        if k in _PASSTHROUGH_KEYS:
            if k == "event" and isinstance(event_dict[k], str):
                event_dict[k] = _redact_string(event_dict[k])
            continue
        event_dict[k] = redact(event_dict[k], k)
    return event_dict


def add_request_id(
    _logger: Any, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Attach the current request id (set by the request-id middleware)."""
    rid = request_id_var.get()
    if rid is not None:
        event_dict.setdefault("request_id", rid)
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging to emit one JSON object per line on stdout."""
    log_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            add_request_id,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redaction_processor,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger (typed as Any because structlog proxies are dynamic)."""
    return structlog.get_logger(name)
