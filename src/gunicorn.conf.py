"""gunicorn settings (loaded automatically: `make deploy` runs gunicorn from src/)."""

import os

# An empty value must not switch prometheus_client to multiprocess mode.
if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)

from observability.logging_config import build_logging, configure_structlog

_level = os.environ.get("LOG_LEVEL", "INFO").upper()
_fmt = os.environ.get("LOG_FORMAT") or "json"
configure_structlog(_level, _fmt)

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
