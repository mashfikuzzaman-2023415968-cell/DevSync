"""Backend layer checker (spec §5.2): AST scan of `app/` imports.

Rules (a layer may import only the layers listed):
- api          → services, schemas, core, db (only to open the request's DB session)
- services     → repositories, models, schemas, algorithms, integrations, uploads, db, core, services
- repositories → models, db, core
- models       → db, core
- schemas      → core, schemas
- algorithms   → algorithms only (PURE: also no sqlalchemy/fastapi/httpx/redis/time/datetime.now)
- integrations → core
- jobs         → services, repositories, models, db, core, algorithms, integrations, uploads, jobs
- core         → core, db, models (audit writer), schemas
- db           → core, db

Usage: `python scripts/check_layers.py [BACKEND_ROOT]`; exits 1 on violations.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ALLOWED: dict[str, set[str]] = {
    "api": {"api", "services", "schemas", "core", "db"},
    "services": {
        "services",
        "repositories",
        "models",
        "schemas",
        "algorithms",
        "integrations",
        "uploads",
        "db",
        "core",
    },
    "repositories": {"repositories", "models", "db", "core"},
    "models": {"models", "db", "core"},
    "schemas": {"schemas", "core"},
    "algorithms": {"algorithms"},
    "integrations": {"integrations", "core"},
    "jobs": {
        "jobs",
        "services",
        "repositories",
        "models",
        "db",
        "core",
        "algorithms",
        "integrations",
        "uploads",
    },
    "core": {"core", "db", "models", "schemas"},
    "db": {"db", "core"},
    "uploads": {"uploads", "core", "db", "models"},
    "reports": {"reports", "db", "models", "core"},
}
# Third-party modules the pure algorithm layer must never touch.
IMPURE_FOR_ALGORITHMS = {
    "sqlalchemy",
    "fastapi",
    "starlette",
    "httpx",
    "redis",
    "rq",
    "requests",
    "socket",
    "asyncpg",
    "psycopg",
    "time",
    "os",
}


def _layer_of(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 2 and parts[0] == "app":
        return parts[1]
    return None


def check_file(path: Path, backend_root: Path) -> list[str]:
    """Return violation messages for one module."""
    rel = path.relative_to(backend_root).as_posix()
    module = rel.removesuffix(".py").replace("/", ".")
    layer = _layer_of(module)
    if layer is None or layer not in ALLOWED:
        return []
    errors: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets: list[str] = []
        if isinstance(node, ast.Import):
            targets = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            targets = [node.module]
        line = getattr(node, "lineno", 0)
        for target in targets:
            dep_layer = _layer_of(target)
            if dep_layer is not None and dep_layer not in ALLOWED[layer]:
                errors.append(f"{rel}:{line}: layer '{layer}' must not import '{target}'")
            if layer == "algorithms" and target.split(".")[0] in IMPURE_FOR_ALGORITHMS:
                errors.append(f"{rel}:{line}: pure algorithms must not import '{target}'")
        if (
            layer == "algorithms"
            and isinstance(node, ast.Attribute)
            and node.attr in {"now", "utcnow", "today"}
        ):
            errors.append(f"{rel}:{node.lineno}: pure algorithms must not read the clock")
    return errors


def main(argv: list[str]) -> int:
    """CLI entry point."""
    backend_root = Path(argv[1]).resolve() if len(argv) > 1 else Path(__file__).resolve().parents[1]
    errors: list[str] = []
    for path in sorted((backend_root / "app").rglob("*.py")):
        errors.extend(check_file(path, backend_root))
    for e in errors:
        print(e)
    print(f"check_layers: {len(errors)} violation(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
