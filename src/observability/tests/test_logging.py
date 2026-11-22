"""Structured logging: JSON schema, redaction, request middleware, Celery context."""

import io
import json
import logging
import logging.config
import re
from types import SimpleNamespace

import pytest
import structlog
from django.conf import settings
from django.test import override_settings

from observability import celery_signals
from observability.logging_config import (
    REDACTED,
    REQUIRED_FIELDS,
    build_logging,
    configure_structlog,
    hash_email,
)
from observability.middleware import RequestLogMiddleware

MIDDLEWARE_PATH = "observability.middleware.RequestLogMiddleware"
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _snapshot_logging():
    loggers = [logging.getLogger()] + [
        lg
        for lg in logging.root.manager.loggerDict.values()
        if isinstance(lg, logging.Logger)
    ]
    return [
        (lg, list(lg.handlers), lg.level, lg.propagate, lg.disabled) for lg in loggers
    ]


def _restore_logging(snapshot) -> None:
    for lg, handlers, level, propagate, disabled in snapshot:
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate
        lg.disabled = disabled


@pytest.fixture
def log_output(monkeypatch):
    """Configure JSON logging into a buffer; returns a reader of parsed lines."""
    monkeypatch.setenv("SERVICE_NAME", "web")
    monkeypatch.setenv("APP_ENVIRONMENT", "test")
    monkeypatch.setenv("APP_VERSION", "9.9.9")
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
        lines = [line for line in buffer.getvalue().splitlines() if line.strip()]
        return [json.loads(line) for line in lines]  # every line must be JSON

    yield read

    structlog.contextvars.clear_contextvars()
    _restore_logging(snapshot)
    if was_configured:
        structlog.configure(**old_structlog)
    else:
        structlog.reset_defaults()


def _assert_schema(line: dict) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in line]
    assert not missing, f"missing fields {missing} in {line}"
    assert TIMESTAMP_RE.match(line["timestamp"]), line["timestamp"]


# --- schema -----------------------------------------------------------------


def test_structlog_lines_are_json_with_required_fields(log_output):
    structlog.get_logger("app.test").info("thing_done", count=3)

    [line] = log_output()
    _assert_schema(line)
    assert line["event"] == "thing_done"
    assert line["level"] == "info"
    assert line["logger"] == "app.test"
    assert line["count"] == 3
    assert line["service"] == "web"
    assert line["environment"] == "test"
    assert line["version"] == "9.9.9"
    assert line["request_id"] is None
    assert line["trace_id"] is None
    assert line["span_id"] is None


def test_stdlib_loggers_use_the_same_json_schema(log_output):
    logging.getLogger("django").warning("plain %s message", "django")
    logging.getLogger("celery.task").info("celery line", extra={"task_kind": "x"})

    django_line, celery_line = log_output()
    for line in (django_line, celery_line):
        _assert_schema(line)
    assert django_line["event"] == "plain django message"
    assert django_line["logger"] == "django"
    assert django_line["level"] == "warning"
    assert celery_line["task_kind"] == "x"


def test_django_request_records_drop_the_request_object(log_output, rf):
    request = rf.get("/candidates/?token=abc")
    logging.getLogger("django.request").warning(
        "Not Found: %s", "/x", extra={"status_code": 404, "request": request}
    )

    [line] = log_output()
    _assert_schema(line)
    assert line["status_code"] == 404
    assert "request" not in line


def test_third_party_loggers_are_at_warning(log_output):
    logging.getLogger("httpx").info("noise")
    logging.getLogger("urllib3").info("noise")
    logging.getLogger("elasticsearch").info("noise")
    logging.getLogger("httpx").warning("kept")

    assert [line["event"] for line in log_output()] == ["kept"]


def test_context_vars_and_exception_fields(log_output):
    structlog.contextvars.bind_contextvars(request_id="req-1")
    log = structlog.get_logger("app.test")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("thing_failed")
    try:
        raise KeyError("missing")
    except KeyError:
        logging.getLogger("django").exception("stdlib failure")

    structlog_line, stdlib_line = log_output()
    assert structlog_line["request_id"] == "req-1"
    assert structlog_line["level"] == "error"
    assert structlog_line["exc_type"] == "ValueError"
    assert structlog_line["exc_message"] == "boom"
    assert isinstance(structlog_line["stack"], str)
    assert "Traceback" in structlog_line["stack"]
    assert stdlib_line["exc_type"] == "KeyError"
    assert stdlib_line["request_id"] == "req-1"


def test_trace_ids_come_from_the_current_otel_span(log_output):
    from opentelemetry import trace  # noqa: PLC0415

    context = trace.SpanContext(
        trace_id=0x1234,
        span_id=0xABCD,
        is_remote=False,
        trace_flags=trace.TraceFlags(1),
    )
    with trace.use_span(trace.NonRecordingSpan(context)):
        structlog.get_logger("app.test").info("traced")

    [line] = log_output()
    assert line["trace_id"] == f"{0x1234:032x}"
    assert len(line["trace_id"]) == 32
    assert line["span_id"] == f"{0xABCD:016x}"
    assert len(line["span_id"]) == 16


def test_types_are_fixed(log_output):
    structlog.get_logger("t").info(
        "typed", status_code="201", duration_ms=3, user_id="7"
    )

    [line] = log_output()
    assert line["status_code"] == 201
    assert line["duration_ms"] == 3.0
    assert isinstance(line["duration_ms"], float)
    assert line["user_id"] == 7


# --- redaction --------------------------------------------------------------


def test_secrets_are_redacted_and_emails_hashed(log_output):
    structlog.get_logger("t").info(
        "sensitive",
        password="hunter2-secret",  # noqa: S106
        Authorization="Bearer abc.def",
        cookie="sessionid=xyz",
        api_key="sk-live-123",
        nested={"user_password": "hunter2-secret", "inner": {"csrftoken": "tok"}},
        contact_email="Sara@Example.com",
        note="mail sara@example.com now",
        card="4111 1111 1111 1111",
        plain_card="4111111111111111",
    )
    logging.getLogger("django").info("stdlib", extra={"passwd": "hunter2-secret"})

    raw = json.dumps(log_output())
    for secret in ("hunter2-secret", "abc.def", "xyz", "sk-live-123", '"tok"'):
        assert secret not in raw
    assert "example.com" not in raw.lower()
    assert "4111" not in raw

    line, stdlib_line = log_output()
    assert line["password"] == REDACTED
    assert line["Authorization"] == REDACTED
    assert line["cookie"] == REDACTED
    assert line["nested"]["user_password"] == REDACTED
    assert line["nested"]["inner"]["csrftoken"] == REDACTED
    expected = hash_email("sara@example.com")
    assert expected.startswith("sha256:")
    assert len(expected) == len("sha256:") + 12
    assert line["contact_email"] == expected
    assert line["note"] == f"mail {expected} now"
    assert line["card"] == "[REDACTED_CARD]"
    assert line["plain_card"] == "[REDACTED_CARD]"
    assert stdlib_line["passwd"] == REDACTED


def test_console_format_builds():
    config = build_logging("debug", "console")
    assert set(config["formatters"]) == {"console"}
    assert config["root"]["level"] == "DEBUG"
    for name in ("django", "gunicorn.access", "celery"):
        assert config["loggers"][name]["handlers"] == []
        assert config["loggers"][name]["propagate"] is True


# --- middleware -------------------------------------------------------------


def _middleware():
    # Once settings.py lists it, keep a single instance (at the top).
    rest = [entry for entry in settings.MIDDLEWARE if entry != MIDDLEWARE_PATH]
    return [MIDDLEWARE_PATH, *rest]


def _request_lines(lines: list[dict]) -> list[dict]:
    return [line for line in lines if line["event"] == "http_request"]


@pytest.mark.django_db
def test_request_line_uses_route_template(
    log_output, client, make_employer, make_candidate, make_posting
):
    posting = make_posting(make_employer())
    candidate = make_candidate()
    client.force_login(candidate.user)

    with override_settings(MIDDLEWARE=_middleware()):
        response = client.get(
            f"/candidates/jobs/{posting.pk}/", headers={"X-Request-ID": "verify-123"}
        )

    assert response.status_code == 200
    assert response["X-Request-ID"] == "verify-123"
    [line] = _request_lines(log_output())
    _assert_schema(line)
    assert line["path"] == "candidates/jobs/<int:pk>/"
    assert line["method"] == "GET"
    assert line["status_code"] == 200
    assert isinstance(line["duration_ms"], float)
    assert line["request_id"] == "verify-123"
    assert line["user_id"] == candidate.user.pk
    assert line["client_ip"] == "127.0.0.1"
    assert line["level"] == "info"
    # The context is cleared once the request is done.
    assert structlog.contextvars.get_contextvars() == {}


@pytest.mark.django_db
def test_invalid_request_id_is_replaced_and_404_is_unmatched(log_output, client):
    with override_settings(MIDDLEWARE=_middleware()):
        response = client.get("/no/such/page/", headers={"X-Request-ID": "bad id!"})

    request_id = response["X-Request-ID"]
    assert request_id != "bad id!"
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    lines = log_output()
    [line] = _request_lines(lines)
    assert line["path"] == "<unmatched>"
    assert line["status_code"] == 404
    assert line["level"] == "warning"
    assert line["request_id"] == request_id
    assert line["user_id"] is None
    for each in lines:
        _assert_schema(each)


def test_forwarded_for_only_when_trusted(rf):
    from observability.middleware import client_ip  # noqa: PLC0415

    request = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6")
    with override_settings(LOG_TRUST_FORWARDED_FOR=False):
        assert client_ip(request) == "10.0.0.1"
    with override_settings(LOG_TRUST_FORWARDED_FOR=True):
        assert client_ip(request) == "1.2.3.4"


def test_exceptions_are_logged_and_reraised(log_output, rf):
    def broken_view(request):
        raise RuntimeError("kaput")

    middleware = RequestLogMiddleware(broken_view)
    with pytest.raises(RuntimeError):
        middleware(rf.get("/x/"))

    failed, request_line = log_output()
    assert failed["event"] == "http_request_failed"
    assert failed["exc_type"] == "RuntimeError"
    assert request_line["event"] == "http_request"
    assert request_line["status_code"] == 500
    assert request_line["level"] == "error"
    assert structlog.contextvars.get_contextvars() == {}


# --- celery -----------------------------------------------------------------


def test_celery_request_id_goes_through_headers(log_output):
    structlog.contextvars.bind_contextvars(request_id="req-from-web")
    headers: dict = {}
    celery_signals.add_request_id_header(headers=headers)
    assert headers == {"request_id": "req-from-web"}

    # Worker side: an empty context, the header arrives on task.request.
    structlog.contextvars.clear_contextvars()
    task = SimpleNamespace(name="applications.tasks.x", request=SimpleNamespace())
    task.request.request_id = "req-from-web"
    celery_signals.bind_task_context(task_id="t-1", task=task)
    structlog.get_logger("applications.tasks").info("job_done")
    celery_signals.clear_task_context(task_id="t-1", task=task)

    [line] = log_output()
    assert line["request_id"] == "req-from-web"
    assert line["task_id"] == "t-1"
    assert line["task_name"] == "applications.tasks.x"
    assert structlog.contextvars.get_contextvars() == {}


def test_celery_task_without_header_gets_new_id_and_restores_context():
    structlog.contextvars.clear_contextvars()
    task = SimpleNamespace(name="t", request=SimpleNamespace(headers=None))
    celery_signals.bind_task_context(task_id="t-2", task=task)
    bound = structlog.contextvars.get_contextvars()
    assert re.fullmatch(r"[0-9a-f]{32}", bound["request_id"])
    celery_signals.clear_task_context(task_id="t-2", task=task)
    assert structlog.contextvars.get_contextvars() == {}

    # Eager task inside a request: the request context comes back afterwards.
    structlog.contextvars.bind_contextvars(request_id="outer", user_id=5)
    celery_signals.bind_task_context(task_id="t-3", task=task)
    assert structlog.contextvars.get_contextvars()["request_id"] == "outer"
    celery_signals.clear_task_context(task_id="t-3", task=task)
    assert structlog.contextvars.get_contextvars() == {
        "request_id": "outer",
        "user_id": 5,
    }
    structlog.contextvars.clear_contextvars()


def test_no_publish_header_without_request_id():
    structlog.contextvars.clear_contextvars()
    headers: dict = {}
    celery_signals.add_request_id_header(headers=headers)
    assert headers == {}
