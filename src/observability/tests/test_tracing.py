"""OpenTelemetry tracing: setup, Django server spans, log correlation, sampling.

No test sets the global tracer provider: spans go to an in-memory exporter
through the provider handed to the instrumentors, and every test uninstruments.
"""

import io
import json
import logging.config
import re

import pytest
import structlog
from django.conf import settings
from opentelemetry import trace
from opentelemetry.instrumentation.django import DjangoInstrumentor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind

from observability import tracing
from observability.logging_config import build_logging, configure_structlog
from observability.tests.test_logging import _restore_logging, _snapshot_logging

OTEL_ENV = (
    "OTEL_ENABLED",
    "OTEL_TRACES_SAMPLER",
    "OTEL_TRACES_SAMPLER_ARG",
    "OTEL_PYTHON_DJANGO_EXCLUDED_URLS",
    "OTEL_PYTHON_EXCLUDED_URLS",
)
HEX32 = re.compile(r"^[0-9a-f]{32}$")
OTEL_MIDDLEWARE = DjangoInstrumentor._opentelemetry_middleware


@pytest.fixture
def clean_env(monkeypatch):
    for name in OTEL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SERVICE_NAME", "web")
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    return monkeypatch


@pytest.fixture
def spans(clean_env):
    """Tracing on, spans in memory; everything is undone afterwards."""
    clean_env.setenv("OTEL_ENABLED", "true")
    clean_env.setenv("OTEL_TRACES_SAMPLER_ARG", "1.0")
    middleware = list(settings.MIDDLEWARE)
    global_provider = trace.get_tracer_provider()
    exporter = InMemorySpanExporter()

    def setup(**kwargs) -> InMemorySpanExporter:
        assert tracing.setup_tracing(exporter=exporter, set_global=False, **kwargs)
        return exporter

    yield setup

    tracing.shutdown_tracing()
    settings.MIDDLEWARE = middleware
    assert not DjangoInstrumentor().is_instrumented_by_opentelemetry
    assert trace.get_tracer_provider() is global_provider


@pytest.fixture
def log_lines(clean_env):
    """JSON logging into a buffer (same approach as test_logging.log_output)."""
    snapshot = _snapshot_logging()
    was_configured = structlog.is_configured()
    old_structlog = structlog.get_config()
    buffer = io.StringIO()
    config = build_logging("INFO", "json")
    config["handlers"]["stdout"]["stream"] = buffer
    configure_structlog("INFO", "json")
    logging.config.dictConfig(config)
    structlog.contextvars.clear_contextvars()

    def read() -> list[dict]:
        return [json.loads(line) for line in buffer.getvalue().splitlines() if line]

    yield read

    structlog.contextvars.clear_contextvars()
    _restore_logging(snapshot)
    if was_configured:
        structlog.configure(**old_structlog)
    else:
        structlog.reset_defaults()


def _server_spans(exporter: InMemorySpanExporter) -> list:
    return [s for s in exporter.get_finished_spans() if s.kind == SpanKind.SERVER]


# --- setup -------------------------------------------------------------------


def test_disabled_by_default(clean_env):
    global_provider = trace.get_tracer_provider()
    assert tracing.setup_tracing() is False
    assert tracing.get_provider() is None
    assert trace.get_tracer_provider() is global_provider
    assert not DjangoInstrumentor().is_instrumented_by_opentelemetry
    assert OTEL_MIDDLEWARE not in settings.MIDDLEWARE


def test_setup_is_idempotent_and_sets_resource(spans):
    spans()
    provider = tracing.get_provider()
    assert provider is not None
    assert tracing.setup_tracing(exporter=InMemorySpanExporter(), set_global=False)
    assert tracing.get_provider() is provider
    assert settings.MIDDLEWARE[0] == OTEL_MIDDLEWARE
    assert settings.MIDDLEWARE.count(OTEL_MIDDLEWARE) == 1
    attributes = provider.resource.attributes
    assert attributes["service.name"] == "web"
    assert attributes["service.version"] == "9.9.9"
    assert attributes["deployment.environment.name"] == "test"


def test_setup_failure_is_logged_not_raised(clean_env, log_lines, monkeypatch):
    clean_env.setenv("OTEL_ENABLED", "true")

    def broken(exporter=None):
        raise RuntimeError("no exporter")

    monkeypatch.setattr(tracing, "build_provider", broken)
    assert tracing.setup_tracing(set_global=False) is False
    assert tracing.get_provider() is None
    [line] = log_lines()
    assert line["event"] == "tracing_setup_failed"
    assert line["exc_type"] == "RuntimeError"


def test_sampler_ratio_and_env_override(clean_env):
    assert tracing.sample_ratio() == pytest.approx(0.1)
    clean_env.setenv("OTEL_TRACES_SAMPLER_ARG", "0.25")
    sampler = tracing.build_sampler()
    assert sampler is not None
    description = sampler.get_description()
    assert description.startswith("ParentBased")
    assert "0.25" in description
    clean_env.setenv("OTEL_TRACES_SAMPLER_ARG", "nonsense")
    assert tracing.sample_ratio() == pytest.approx(0.1)
    clean_env.setenv("OTEL_TRACES_SAMPLER_ARG", "7")
    assert tracing.sample_ratio() == 1.0
    clean_env.setenv("OTEL_TRACES_SAMPLER", "always_on")
    assert tracing.build_sampler() is None  # the SDK reads the env itself


def test_celery_can_be_added_later(spans):
    from opentelemetry.instrumentation.celery import CeleryInstrumentor  # noqa: PLC0415

    spans()
    assert not CeleryInstrumentor().is_instrumented_by_opentelemetry
    assert tracing.setup_tracing(celery=True)
    assert CeleryInstrumentor().is_instrumented_by_opentelemetry


# --- requests ----------------------------------------------------------------


@pytest.mark.django_db
def test_request_creates_server_span_with_route_and_same_trace_id_in_log(
    spans, log_lines, client, make_employer, make_candidate, make_posting
):
    exporter = spans()
    posting = make_posting(make_employer())
    client.force_login(make_candidate().user)

    response = client.get(f"/candidates/jobs/{posting.pk}/")

    assert response.status_code == 200
    [span] = _server_spans(exporter)
    assert span.attributes["http.route"] == "candidates/jobs/<int:pk>/"
    trace_id = format(span.context.trace_id, "032x")
    [line] = [each for each in log_lines() if each["event"] == "http_request"]
    assert HEX32.match(line["trace_id"])
    assert line["trace_id"] == trace_id
    assert line["span_id"] == format(span.context.span_id, "016x")


@pytest.mark.django_db
def test_incoming_traceparent_is_honoured(spans, clean_env, client):
    # Ratio 0: only a sampled parent can get this request recorded.
    clean_env.setenv("OTEL_TRACES_SAMPLER_ARG", "0")
    exporter = spans()
    parent_trace = "4bf92f3577b34da6a3ce929d0e0e4736"
    parent_span = "00f067aa0ba902b7"

    client.get("/", headers={"traceparent": f"00-{parent_trace}-{parent_span}-01"})
    client.get("/")  # no parent: the ratio (0) decides

    [span] = _server_spans(exporter)
    assert format(span.context.trace_id, "032x") == parent_trace
    assert format(span.parent.span_id, "016x") == parent_span
    assert span.parent.is_remote


@pytest.mark.django_db
def test_metrics_and_static_are_not_traced(spans, client):
    exporter = spans()
    client.get("/metrics")
    client.get("/static/css/app.css")
    assert _server_spans(exporter) == []
