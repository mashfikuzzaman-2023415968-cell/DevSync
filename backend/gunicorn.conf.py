"""Gunicorn settings (spec §15.3): Uvicorn workers, timeouts, worker recycling."""

import multiprocessing
import os

bind = "0.0.0.0:8000"
worker_class = "uvicorn.workers.UvicornWorker"
_configured = int(os.environ.get("GUNICORN_WORKERS", "0") or 0)
workers = _configured or multiprocessing.cpu_count() * 2 + 1
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = 20
keepalive = 5
max_requests = int(os.environ.get("MAX_REQUESTS", "1000"))
max_requests_jitter = 100
forwarded_allow_ips = os.environ.get("TRUSTED_PROXY_IPS", "127.0.0.1")
accesslog = None  # request logging is structured, from the app
# Heartbeat files on tmpfs: the root filesystem is read-only (spec §14.12).
worker_tmp_dir = "/dev/shm"  # noqa: S108 - private per-container tmpfs, not a shared temp dir
