"""Sentry error reporting (sentry-sdk 2.x). Off while ``SENTRY_DSN`` is empty.

* ``send_default_pii=False``: no user e-mail/IP/cookies are attached by the SDK,
  and the SDK's default ``EventScrubber`` masks denylisted keys (passwords,
  tokens, ...) in frame variables. sentry-sdk 2.75 marks ``send_default_pii`` as
  deprecated in favour of ``data_collection``; it is kept on purpose, because
  passing ``data_collection`` disables that default scrubber.
  :func:`before_send` also strips cookies, auth headers and request bodies
  (defence in depth, in case an integration or a later option adds them).
* ``traces_sample_rate``: ``SENTRY_TRACES_SAMPLE_RATE`` (0 by default). OTel does
  the tracing; 0 is passed as ``None``, which turns Sentry performance monitoring
  off completely instead of creating unsampled transactions on every request.
* Every event is tagged with ``request_id`` (structlog context), ``trace_id`` (the
  current OTel span, so an error links to its Jaeger trace) and ``service``.
* Logging: the default ``LoggingIntegration`` stays (INFO records become
  breadcrumbs, ERROR records become events). Exceptions are not reported twice:
  the Django/Celery integrations and our ``exc_info`` log lines carry the same
  exception object, which the default ``DedupeIntegration`` drops. The
  ``http_request`` access line of ``observability.middleware`` is error level
  for every 5xx and has no exception, so that logger is ignored for Sentry;
  the 5xx itself is reported by the Django integration.
* The release is ``APP_VERSION``; the environment is ``SENTRY_ENVIRONMENT``,
  falling back to ``APP_ENVIRONMENT``.
"""

from __future__ import annotations

import os
from typing import Any

import sentry_sdk
import structlog
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import ignore_logger

logger = structlog.get_logger(__name__)

# Lower-case header names removed from every event.
SCRUBBED_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-csrftoken",
        "x-api-key",
    }
)
# The per-request access log line (error level for 5xx, no exception).
IGNORED_LOGGERS = ("observability.middleware",)

_initialised_dsn: str | None = None


def _sample_rate() -> float | None:
    raw = os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "").strip()
    try:
        rate = float(raw) if raw else 0.0
    except ValueError:
        rate = 0.0
    return min(rate, 1.0) if rate > 0 else None


def _trace_id() -> str | None:
    try:
        from opentelemetry import trace  # noqa: PLC0415
    except ImportError:  # pragma: no cover - opentelemetry-api is a dependency
        return None
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def _scrub_request(request: dict[str, Any]) -> None:
    request.pop("cookies", None)
    request.pop("data", None)  # bodies: form posts, JSON, uploads
    headers = request.get("headers")
    if isinstance(headers, dict):
        for name in list(headers):
            if str(name).lower() in SCRUBBED_HEADERS:
                del headers[name]
    elif isinstance(headers, list):  # [[name, value], ...] form
        request["headers"] = [
            pair
            for pair in headers
            if not (
                isinstance(pair, list | tuple)
                and pair
                and str(pair[0]).lower() in SCRUBBED_HEADERS
            )
        ]


def before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Add correlation tags and remove request secrets. Never drops the event."""
    del hint
    tags = event.setdefault("tags", {})
    if isinstance(tags, dict):
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        if request_id:
            tags.setdefault("request_id", str(request_id))
        trace_id = _trace_id()
        if trace_id:
            tags.setdefault("trace_id", trace_id)
        tags.setdefault("service", os.environ.get("SERVICE_NAME") or "web")
    request = event.get("request")
    if isinstance(request, dict):
        _scrub_request(request)
    user = event.get("user")
    if isinstance(user, dict):  # keep only the numeric id, never e-mail/IP
        event["user"] = {"id": user["id"]} if "id" in user else {}
    return event


def setup_sentry(**overrides: Any) -> bool:
    """Initialise the SDK once per DSN; True when Sentry is active.

    ``overrides`` are passed to ``sentry_sdk.init`` (tests use ``transport``).
    """
    global _initialised_dsn  # noqa: PLW0603
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    if _initialised_dsn == dsn and sentry_sdk.get_client().is_active():
        return True
    try:
        for name in IGNORED_LOGGERS:
            ignore_logger(name)
        options: dict[str, Any] = {
            "dsn": dsn,
            "environment": (
                os.environ.get("SENTRY_ENVIRONMENT")
                or os.environ.get("APP_ENVIRONMENT")
                or "development"
            ),
            "release": os.environ.get("APP_VERSION") or "0.1.0",
            "send_default_pii": False,
            "traces_sample_rate": _sample_rate(),
            "integrations": [DjangoIntegration(), CeleryIntegration()],
            "before_send": before_send,
        }
        options.update(overrides)
        sentry_sdk.init(**options)
    except Exception:  # a bad DSN must not take the app down
        logger.exception("sentry_setup_failed")
        return False
    _initialised_dsn = dsn
    return True


def shutdown_sentry() -> None:
    """Flush and drop the client (tests, shutdown)."""
    global _initialised_dsn  # noqa: PLW0603
    client = sentry_sdk.get_client()
    if client.is_active():
        client.close()
    sentry_sdk.get_global_scope().set_client(None)
    _initialised_dsn = None
