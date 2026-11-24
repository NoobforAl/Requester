"""Protected Prometheus export and gunicorn multiprocess helpers.

`metrics_view` wraps django-prometheus' `ExportToDjangoView`, which already
switches to a `MultiProcessCollector` registry when `PROMETHEUS_MULTIPROC_DIR`
is set in the environment. This module only adds access control:

* `METRICS_TOKEN` (str): required. Empty means the endpoint does not exist (404).
  The request must send `Authorization: Bearer <token>`.
* `METRICS_ALLOWED_IPS` (list of CIDRs): optional. When non-empty, `REMOTE_ADDR`
  must also fall inside one of them. `X-Forwarded-For` is ignored on purpose,
  because a client can set it to anything.

Every refusal is a plain 404 so the endpoint is not discoverable.
"""

from __future__ import annotations

import hmac
import ipaddress
import os
from typing import Any

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.views.decorators.cache import never_cache
from django_prometheus.exports import ExportToDjangoView
from prometheus_client import multiprocess

_BEARER_PREFIX = "bearer "


def multiprocess_enabled() -> bool:
    """Return True when prometheus_client runs in multiprocess mode."""
    return bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))


def _token_ok(request: HttpRequest) -> bool:
    expected = str(getattr(settings, "METRICS_TOKEN", "") or "")
    if not expected:
        return False
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith(_BEARER_PREFIX):
        return False
    supplied = header[len(_BEARER_PREFIX) :].strip()
    return hmac.compare_digest(supplied.encode(), expected.encode())


def _ip_ok(request: HttpRequest) -> bool:
    allowed = getattr(settings, "METRICS_ALLOWED_IPS", None) or []
    if not allowed:
        return True
    try:
        client = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return False
    for cidr in allowed:
        try:
            if client in ipaddress.ip_network(cidr, strict=False):
                return True
        except ValueError:
            # A malformed entry never grants access.
            continue
    return False


@never_cache
def metrics_view(request: HttpRequest) -> HttpResponse:
    """Serve Prometheus metrics to authorised scrapers only, 404 otherwise.

    Any refusal, including a non-GET method, is a 404 so the endpoint stays hidden.
    """
    if request.method != "GET" or not (_token_ok(request) and _ip_ok(request)):
        raise Http404
    return ExportToDjangoView(request)


def child_exit(_server: Any, worker: Any) -> None:
    """Gunicorn `child_exit` hook: drop the dead worker's live gauges.

    Without this, gauges with `multiprocess_mode="live*"` keep reporting
    values from workers that no longer exist.
    """
    if not multiprocess_enabled():
        return
    multiprocess.mark_process_dead(worker.pid)
