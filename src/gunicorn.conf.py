"""gunicorn settings (loaded automatically: `make deploy` runs gunicorn from src/)."""

import os

from observability.logging_config import build_logging, configure_structlog

_level = os.environ.get("LOG_LEVEL", "INFO").upper()
_fmt = os.environ.get("LOG_FORMAT") or "json"
configure_structlog(_level, _fmt)

# gunicorn.error propagates to our root handler, so its lines are JSON too.
logconfig_dict = build_logging(_level, _fmt)
# RequestLogMiddleware already logs every request as `http_request`.
accesslog = None
errorlog = "-"
