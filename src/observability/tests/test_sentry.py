"""Sentry: off without a DSN; events carry correlation tags and no PII/secrets.

A fake DSN plus an in-process transport: nothing leaves the process. The client
is closed and removed after each test, so later tests see an inactive SDK.
"""

import pytest
import sentry_sdk
import structlog
from opentelemetry import trace
from sentry_sdk.transport import Transport

from observability import sentry
from observability.sentry import before_send, setup_sentry, shutdown_sentry

FAKE_DSN = "https://public@sentry.invalid/1"
# sentry-sdk 2.75 deprecates send_default_pii in favour of data_collection; we keep
# it on purpose (see observability/sentry.py).
pytestmark = pytest.mark.filterwarnings(
    "ignore:The send_default_pii option is deprecated:DeprecationWarning"
)


class CaptureTransport(Transport):
    def __init__(self):
        super().__init__()
        self.envelopes = []

    def capture_envelope(self, envelope):
        self.envelopes.append(envelope)

    def events(self) -> list[dict]:
        found = []
        for envelope in self.envelopes:
            event = envelope.get_event()
            if event is not None:
                found.append(event)
        return found


@pytest.fixture
def sentry_env(monkeypatch):
    for name in ("SENTRY_DSN", "SENTRY_ENVIRONMENT", "SENTRY_TRACES_SAMPLE_RATE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SERVICE_NAME", "tasks")
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    structlog.contextvars.clear_contextvars()
    yield monkeypatch
    structlog.contextvars.clear_contextvars()
    shutdown_sentry()
    assert not sentry_sdk.get_client().is_active()


@pytest.fixture
def transport(sentry_env):
    sentry_env.setenv("SENTRY_DSN", FAKE_DSN)
    capture = CaptureTransport()
    assert setup_sentry(transport=capture)
    return capture


def test_no_dsn_means_not_initialised(sentry_env):
    assert setup_sentry() is False
    assert not sentry_sdk.get_client().is_active()


def test_options(transport):
    options = sentry_sdk.get_client().options
    assert options["send_default_pii"] is False
    assert options["environment"] == "test"
    assert options["release"] == "9.9.9"
    assert options["traces_sample_rate"] is None  # 0 = Sentry tracing off
    assert options["before_send"] is before_send
    names = {
        type(each).__name__ for each in sentry_sdk.get_client().integrations.values()
    }
    assert {"DjangoIntegration", "CeleryIntegration"} <= names
    # Idempotent for the same DSN: the client is kept.
    client = sentry_sdk.get_client()
    assert setup_sentry()
    assert sentry_sdk.get_client() is client


def test_sentry_environment_wins(sentry_env):
    sentry_env.setenv("SENTRY_DSN", FAKE_DSN)
    sentry_env.setenv("SENTRY_ENVIRONMENT", "staging")
    sentry_env.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.5")
    assert setup_sentry(transport=CaptureTransport())
    options = sentry_sdk.get_client().options
    assert options["environment"] == "staging"
    assert options["traces_sample_rate"] == 0.5


def test_exception_event_has_tags_and_no_pii(transport):
    structlog.contextvars.bind_contextvars(request_id="req-42")
    context = trace.SpanContext(
        trace_id=0x1234,
        span_id=0xABCD,
        is_remote=False,
        trace_flags=trace.TraceFlags(1),
    )
    with trace.use_span(trace.NonRecordingSpan(context)):
        sentry_sdk.set_user({"id": 7, "email": "sara@example.com"})
        try:
            raise ValueError("boom")
        except ValueError as exc:
            sentry_sdk.capture_exception(exc)
    sentry_sdk.flush()

    [event] = transport.events()
    assert event["tags"]["request_id"] == "req-42"
    assert event["tags"]["trace_id"] == f"{0x1234:032x}"
    assert event["tags"]["service"] == "tasks"
    assert event["exception"]["values"][0]["type"] == "ValueError"
    assert event["user"] == {"id": 7}
    assert "sara@example.com" not in repr(event.get("user"))
    assert "request" not in event or "cookies" not in event["request"]


def test_before_send_scrubs_request_secrets(sentry_env):
    event = {
        "request": {
            "url": "http://testserver/x",
            "cookies": {"sessionid": "secret-session"},
            "data": {"password": "hunter2"},
            "headers": {
                "Authorization": "Bearer abc",
                "Cookie": "sessionid=secret-session",
                "X-CSRFToken": "tok",
                "User-Agent": "pytest",
            },
        },
        "user": {"id": 3, "ip_address": "1.2.3.4", "email": "a@b.cd"},
    }
    result = before_send(event, {})
    assert result is event
    request = result["request"]
    assert "cookies" not in request
    assert "data" not in request
    assert request["headers"] == {"User-Agent": "pytest"}
    assert result["user"] == {"id": 3}
    assert result["tags"] == {"service": "tasks"}

    listed = before_send(
        {"request": {"headers": [["authorization", "x"], ["Accept", "*/*"]]}}, {}
    )
    assert listed["request"]["headers"] == [["Accept", "*/*"]]


def test_middleware_access_logger_is_ignored(transport):
    import logging  # noqa: PLC0415

    logging.getLogger(sentry.IGNORED_LOGGERS[0]).error("http_request")
    logging.getLogger("applications.tasks").error("task_broke")
    sentry_sdk.flush()

    messages = [
        event.get("logentry", {}).get("message") for event in transport.events()
    ]
    assert messages == ["task_broke"]
