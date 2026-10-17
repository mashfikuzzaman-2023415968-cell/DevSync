"""OpenAPI contract linter and drift check (spec §10.4).

Checks every operation in the app's OpenAPI document:
- has a summary and at least one example on its success response;
- declares 401/403/404 (unless public), 422 (if it takes a body or parameters)
  — public operations are listed in PUBLIC_OPERATIONS;
- uses no untyped object schemas (`{"type": "object"}` without properties,
  additionalProperties or $ref) anywhere in request or response bodies.

`--write` regenerates `docs/api/openapi.json`; without it the committed file
must match the code exactly (drift fails the gate).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
# OPENAPI_PATH lets the containerized gate point at the mounted docs folder.
COMMITTED = Path(os.environ.get("OPENAPI_PATH", REPO_ROOT / "docs" / "api" / "openapi.json"))

# Operations reachable without a session (spec §10.2 "Public endpoints").
PUBLIC_OPERATIONS: set[tuple[str, str]] = {
    ("get", "/api/v1/health"),
    ("get", "/api/v1/health/ready"),
    ("get", "/api/v1/captcha/challenge"),
    ("get", "/api/v1/public/stats"),
    ("post", "/api/v1/client-errors"),
    ("get", "/api/v1/auth/csrf"),
    ("post", "/api/v1/auth/register"),
    ("post", "/api/v1/auth/login"),
    ("post", "/api/v1/auth/login/totp"),
    ("post", "/api/v1/auth/email/verify"),
    ("post", "/api/v1/auth/password/forgot"),
    ("post", "/api/v1/auth/password/reset"),
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def build_openapi() -> dict[str, Any]:
    """Generate the OpenAPI document from the app (development settings expose it)."""
    from app.core.config import Environment, Settings  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    app = create_app(Settings(DEVSYNC_ENV=Environment.DEVELOPMENT, ALLOWED_HOSTS="localhost"))
    return app.openapi()


def _untyped_objects(schema: Any, where: str) -> list[str]:
    problems: list[str] = []
    if isinstance(schema, dict):
        if (
            schema.get("type") == "object"
            and "properties" not in schema
            and "additionalProperties" not in schema
            and "$ref" not in schema
        ):
            problems.append(f"{where}: untyped object schema")
        for key, value in schema.items():
            problems.extend(_untyped_objects(value, f"{where}.{key}"))
    elif isinstance(schema, list):
        for i, value in enumerate(schema):
            problems.extend(_untyped_objects(value, f"{where}[{i}]"))
    return problems


def lint(spec: dict[str, Any]) -> list[str]:
    """Return contract problems (pure; unit-tested)."""
    problems: list[str] = []
    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method not in HTTP_METHODS:
                continue
            where = f"{method.upper()} {path}"
            if not op.get("summary"):
                problems.append(f"{where}: missing summary")
            responses = op.get("responses", {})
            success = [c for c in responses if str(c).startswith("2")]
            if not success:
                problems.append(f"{where}: no success response")
            for code in success:
                content = responses[code].get("content", {}).get("application/json", {})
                if content and "example" not in content and "examples" not in content:
                    problems.append(f"{where}: success response {code} has no example")
            public = (method, path) in PUBLIC_OPERATIONS
            required: set[str] = set() if public else {"401", "403", "404"}
            if op.get("requestBody") or (op.get("parameters") and not public):
                required.add("422")
            missing = sorted(required - {str(c) for c in responses})
            if missing:
                problems.append(f"{where}: missing declared responses {missing}")
            problems.extend(_untyped_objects(op.get("requestBody", {}), f"{where} requestBody"))
            for code, resp in responses.items():
                problems.extend(_untyped_objects(resp.get("content", {}), f"{where} {code}"))
    for name, schema in spec.get("components", {}).get("schemas", {}).items():
        problems.extend(_untyped_objects(schema, f"schema {name}"))
    return problems


def render(spec: dict[str, Any]) -> str:
    """Stable JSON text for the committed contract file."""
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    """CLI entry point."""
    spec = build_openapi()
    problems = lint(spec)
    for p in problems:
        print(f"check_openapi: {p}")
    text = render(spec)
    if "--write" in argv:
        COMMITTED.parent.mkdir(parents=True, exist_ok=True)
        COMMITTED.write_text(text, encoding="utf-8")
        print(f"check_openapi: wrote {COMMITTED}")
    elif not COMMITTED.exists() or COMMITTED.read_text(encoding="utf-8") != text:
        problems.append("docs/api/openapi.json differs from the code (run `make openapi`)")
        print("check_openapi: committed docs/api/openapi.json is out of date")
    print(f"check_openapi: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
