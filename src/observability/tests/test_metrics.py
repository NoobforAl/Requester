"""Tests for the protected Prometheus endpoint and the gunicorn hook.

The module doubles as a tiny ROOT_URLCONF so the tests never depend on the
project urls.py or on PROMETHEUS_ENABLED.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

import pytest
from django.conf import settings
from django.http import Http404, HttpResponse
from django.test import RequestFactory, override_settings
from django.urls import path
from prometheus_client import REGISTRY
from prometheus_client.parser import text_string_to_metric_families

from observability import metrics
from observability.metrics import metrics_view

TOKEN = "test-metrics-token"  # noqa: S105 (test fixture, not a secret)
BEFORE = "django_prometheus.middleware.PrometheusBeforeMiddleware"
AFTER = "django_prometheus.middleware.PrometheusAfterMiddleware"


def ping(request):
    return HttpResponse("pong")


urlpatterns = [
    path("ping", ping, name="test-ping"),
    path("metrics", metrics_view, name="prometheus-metrics"),
]


@pytest.fixture(autouse=True)
def _single_process(monkeypatch):
    # Multiprocess mode is opt-in per test.
    monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
    monkeypatch.delenv("prometheus_multiproc_dir", raising=False)


def _get(auth: str | None = None, remote_addr: str = "127.0.0.1"):
    request = RequestFactory().get("/metrics", REMOTE_ADDR=remote_addr)
    if auth is not None:
        request.META["HTTP_AUTHORIZATION"] = auth
    return metrics_view(request)


def _status(auth: str | None = None, remote_addr: str = "127.0.0.1") -> int:
    try:
        return _get(auth, remote_addr).status_code
    except Http404:
        return 404


@override_settings(METRICS_TOKEN="")
def test_no_token_configured_is_404_even_with_header():
    assert _status() == 404
    assert _status("Bearer ") == 404
    assert _status(f"Bearer {TOKEN}") == 404


@override_settings(METRICS_TOKEN=TOKEN)
@pytest.mark.parametrize(
    "auth",
    [None, "", "Bearer wrong", f"Basic {TOKEN}", TOKEN, f"Bearer {TOKEN}x"],
)
def test_wrong_or_missing_token_is_404(auth):
    assert _status(auth) == 404


@override_settings(METRICS_TOKEN=TOKEN)
def test_right_token_returns_prometheus_text():
    response = _get(f"Bearer {TOKEN}")
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/plain")
    body = response.content.decode()
    names = {family.name for family in text_string_to_metric_families(body)}
    assert "python_info" in names
    # The scheme is case-insensitive (RFC 7235).
    assert _get(f"bearer {TOKEN}").status_code == 200


@override_settings(
    METRICS_TOKEN=TOKEN, METRICS_ALLOWED_IPS=["10.0.0.0/8", "not-a-cidr"]
)
def test_allowed_ips_restrict_access():
    assert _status(f"Bearer {TOKEN}", remote_addr="10.1.2.3") == 200
    assert _status(f"Bearer {TOKEN}", remote_addr="192.168.1.5") == 404
    assert _status(f"Bearer {TOKEN}", remote_addr="garbage") == 404
    # The IP check never replaces the token check.
    assert _status(None, remote_addr="10.1.2.3") == 404


@override_settings(
    METRICS_TOKEN=TOKEN,
    ROOT_URLCONF=__name__,
    MIDDLEWARE=[BEFORE, *settings.MIDDLEWARE, AFTER],
)
def test_middleware_records_requests_and_endpoint_exports_them(client):
    labels = {"status": "200", "view": "test-ping", "method": "GET"}
    sample = "django_http_responses_total_by_status_view_method_total"
    before = REGISTRY.get_sample_value(sample, labels) or 0.0

    assert client.get("/ping").status_code == 200

    assert REGISTRY.get_sample_value(sample, labels) == before + 1
    assert client.get("/metrics").status_code == 404
    response = client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200
    body = response.content.decode()
    assert "django_http_requests_before_middlewares_total" in body
    assert 'view="test-ping"' in body
    assert "django_http_requests_latency_seconds_by_view_method_bucket" in body


@override_settings(METRICS_TOKEN=TOKEN, ROOT_URLCONF=__name__)
def test_post_is_rejected(client):
    response = client.post("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 405


@override_settings(METRICS_TOKEN=TOKEN)
def test_multiprocess_mode_uses_the_multiproc_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    target = "prometheus_client.multiprocess.MultiProcessCollector"
    with mock.patch(target) as collector:
        response = _get(f"Bearer {TOKEN}")
    assert response.status_code == 200
    collector.assert_called_once()


def test_child_exit_marks_worker_dead_only_in_multiprocess_mode(monkeypatch, tmp_path):
    worker = SimpleNamespace(pid=4242)
    with mock.patch.object(metrics.multiprocess, "mark_process_dead") as mark:
        metrics.child_exit(None, worker)
        mark.assert_not_called()

        monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
        metrics.child_exit(None, worker)
        mark.assert_called_once_with(4242)
