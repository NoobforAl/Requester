"""Celery signal handlers for structured logging. Connected when imported.

* ``before_task_publish``: copy the current ``request_id`` into the task headers.
* ``task_prerun``: bind ``request_id`` (from the headers, else a new uuid4),
  ``task_id`` and ``task_name`` to the log context.
* ``task_postrun``: clear that context again.
* ``setup_logging``: a no-op receiver, so Celery keeps Django's ``LOGGING``
  instead of installing its own handlers.

Eager tasks (``CELERY_TASK_ALWAYS_EAGER``) run inside the web request, so the
context that was active before ``task_prerun`` is restored in ``task_postrun``
and the task reuses the caller's ``request_id``.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from celery.signals import before_task_publish, setup_logging, task_postrun, task_prerun

REQUEST_ID_HEADER = "request_id"

# Context that was active before each running task, keyed by task id.
_saved_contexts: dict[str, dict[str, Any]] = {}


@setup_logging.connect(weak=False)
def keep_django_logging(**_: Any) -> None:
    """Connecting any receiver stops Celery from configuring logging itself."""


@before_task_publish.connect(weak=False)
def add_request_id_header(headers: dict[str, Any] | None = None, **_: Any) -> None:
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    if request_id and headers is not None:
        headers.setdefault(REQUEST_ID_HEADER, request_id)


def _header_request_id(task: Any) -> str | None:
    request = getattr(task, "request", None)
    if request is None:
        return None
    value = getattr(request, REQUEST_ID_HEADER, None)
    if not value:
        headers = getattr(request, "headers", None) or {}
        value = headers.get(REQUEST_ID_HEADER)
    return str(value) if value else None


@task_prerun.connect(weak=False)
def bind_task_context(task_id: str | None = None, task: Any = None, **_: Any) -> None:
    previous = structlog.contextvars.get_contextvars()
    if task_id:
        _saved_contexts[task_id] = previous
    request_id = (
        _header_request_id(task) or previous.get("request_id") or uuid.uuid4().hex
    )
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        task_id=task_id,
        task_name=getattr(task, "name", None),
    )


@task_postrun.connect(weak=False)
def clear_task_context(task_id: str | None = None, **_: Any) -> None:
    structlog.contextvars.clear_contextvars()
    previous = _saved_contexts.pop(task_id, None) if task_id else None
    if previous:
        structlog.contextvars.bind_contextvars(**previous)
