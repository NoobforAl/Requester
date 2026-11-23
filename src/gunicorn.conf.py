"""gunicorn settings (loaded automatically: `make deploy` runs gunicorn from src/)."""

import os

# An empty value must not switch prometheus_client to multiprocess mode.
if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)

from observability.logging_config import build_logging, configure_structlog
from requester.runtime import container_cpu_count

_level = os.environ.get("LOG_LEVEL", "INFO").upper()
_fmt = os.environ.get("LOG_FORMAT") or "json"
configure_structlog(_level, _fmt)

bind = "0.0.0.0:8000"
# 2 x CPUs + 1, counted from the container's CPU limit, not the host's CPUs
# (os.cpu_count() would start 17 workers in a 2-CPU, 1 GB container).
# WEB_CONCURRENCY overrides it.
workers = int(os.environ.get("WEB_CONCURRENCY") or 2 * container_cpu_count() + 1)
# Recycle workers now and then so slow memory growth can never reach the limit;
# the jitter keeps them from all restarting at the same moment.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS") or 2000)
max_requests_jitter = max_requests // 10
# Worker heartbeat files in RAM: on a container's overlay filesystem a slow write
# can stall a worker long enough for gunicorn to kill it.
worker_tmp_dir = "/dev/shm"  # noqa: S108  # nosec B108 - the container's own tmpfs

# gunicorn.error propagates to our root handler, so its lines are JSON too.
logconfig_dict = build_logging(_level, _fmt)
# RequestLogMiddleware already logs every request as `http_request`.
accesslog = None
errorlog = "-"


def child_exit(server, worker):
    """Drop a dead worker's metric files (Prometheus multiprocess mode)."""
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess  # noqa: PLC0415

        multiprocess.mark_process_dead(worker.pid)
