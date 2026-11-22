"""Request ID + one structured ``http_request`` log line per request.

Place it near the top of ``MIDDLEWARE`` (right after ``SecurityMiddleware``), so
the request ID is bound before anything else logs.

Client IP: ``REMOTE_ADDR`` by default. The first ``X-Forwarded-For`` entry is used
only when the ``LOG_TRUST_FORWARDED_FOR`` setting is true; when that setting is
absent it follows ``SECURE_PROXY_SSL_HEADER`` (set by ``BEHIND_PROXY=true``),
because then a trusted reverse proxy sits in front of the app.

Bodies, headers and cookies are never logged.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from typing import Any

import structlog
from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = structlog.get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
UNMATCHED_ROUTE = "<unmatched>"


def request_id_from(request: HttpRequest) -> str:
    """The incoming ``X-Request-ID`` when it is well formed, else a new uuid4."""
    incoming = request.headers.get(REQUEST_ID_HEADER, "")
    if _REQUEST_ID_RE.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


def _trust_forwarded_for() -> bool:
    explicit = getattr(settings, "LOG_TRUST_FORWARDED_FOR", None)
    if explicit is not None:
        return bool(explicit)
    return bool(getattr(settings, "SECURE_PROXY_SSL_HEADER", None))


def client_ip(request: HttpRequest) -> str | None:
    if _trust_forwarded_for():
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    return request.META.get("REMOTE_ADDR") or None


def _user_id(request: HttpRequest) -> int | None:
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user.pk
    return None


def _route(request: HttpRequest) -> str:
    match = getattr(request, "resolver_match", None)
    route = getattr(match, "route", None) if match is not None else None
    if route is None:
        return UNMATCHED_ROUTE
    # The site root has the empty route ""; log it as "/" so it stays readable.
    return route or "/"


class RequestLogMiddleware:
    """Bind ``request_id``/``user_id`` to the log context and log the request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request_id_from(request)
        request.request_id = request_id  # type: ignore[attr-defined]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()
        try:
            try:
                response = self.get_response(request)
            except Exception:
                if not getattr(request, "_exception_logged", False):
                    logger.exception("http_request_failed", **self._fields(request))
                self._log(request, 500, start)
                raise
            response[REQUEST_ID_HEADER] = request_id
            self._log(request, response.status_code, start)
            return response
        finally:
            structlog.contextvars.clear_contextvars()

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., Any],
        view_args: Any,
        view_kwargs: Any,
    ) -> None:
        user_id = _user_id(request)
        if user_id is not None:
            structlog.contextvars.bind_contextvars(user_id=user_id)

    def process_exception(self, request: HttpRequest, exception: Exception) -> None:
        """Log view exceptions (Django turns them into a 500 response after this)."""
        request._exception_logged = True  # type: ignore[attr-defined]
        logger.error("http_request_failed", exc_info=exception, **self._fields(request))

    @staticmethod
    def _fields(request: HttpRequest) -> dict[str, Any]:
        return {"method": request.method, "path": _route(request)}

    def _log(self, request: HttpRequest, status_code: int, start: float) -> None:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        if status_code >= 500:  # noqa: PLR2004
            log = logger.error
        elif status_code >= 400:  # noqa: PLR2004
            log = logger.warning
        else:
            log = logger.info
        log(
            "http_request",
            **self._fields(request),
            status_code=int(status_code),
            duration_ms=float(duration_ms),
            # After logout the user is anonymous again; keep the bound id.
            user_id=_user_id(request)
            or structlog.contextvars.get_contextvars().get("user_id"),
            client_ip=client_ip(request),
        )
