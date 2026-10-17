# syntax=docker/dockerfile:1.7
# DevSync backend image (spec §14.12): non-root, read-only-root friendly, hashed deps.
# Targets: `runtime` (api / worker / scheduler) and `dev` (+ test & quality tooling, used by the gate).
# Base image pinned by digest; update deliberately with `make deps-update` (spec §14.21).
ARG PYTHON_IMAGE=python:3.12-slim

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app
RUN apt-get update && apt-get upgrade -y --no-install-recommends \
 && apt-get clean && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 devsync \
 && useradd --system --uid 10001 --gid devsync --home-dir /app --shell /usr/sbin/nologin devsync \
 && python -m venv /opt/venv
WORKDIR /app

FROM base AS runtime-deps
COPY requirements.lock .
RUN pip install --require-hashes --no-deps -r requirements.lock

FROM runtime-deps AS dev-deps
COPY requirements-dev.lock .
RUN pip install --require-hashes --no-deps -r requirements-dev.lock

FROM runtime-deps AS runtime
COPY --chown=root:root app ./app
COPY --chown=root:root alembic ./alembic
COPY --chown=root:root alembic.ini gunicorn.conf.py pyproject.toml ./
COPY --chown=root:root scripts ./scripts
USER 10001:10001
EXPOSE 8000
# Sends an allowed Host header: TrustedHostMiddleware rejects bare 127.0.0.1 (spec §14.3).
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; r=urllib.request.Request('http://127.0.0.1:8000/api/v1/health', headers={'Host': 'api'}); sys.exit(0 if urllib.request.urlopen(r, timeout=2).status==200 else 1)"
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app.main:app_factory()"]

FROM dev-deps AS dev
COPY --chown=root:root . .
USER 10001:10001
CMD ["pytest", "-q"]
