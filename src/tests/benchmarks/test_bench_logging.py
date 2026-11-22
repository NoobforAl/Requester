"""Benchmarks of the structured-logging pipeline (``observability.logging_config``).

The formatter is built locally, so the global logging configuration is untouched.
"""

import json
import logging

import pytest

logging_config = pytest.importorskip("observability.logging_config")


@pytest.fixture
def formatter() -> logging.Formatter:
    config = logging_config.formatter_config("json")
    factory = config.pop("()")
    return factory(**config)


def _record(msg: str, *args, **extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="candidates.views",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )
    record.__dict__.update(extra)
    return record


@pytest.mark.benchmark(group="logging")
def test_bench_render_stdlib_record(benchmark, formatter):
    """A foreign (stdlib) record through the full pre-chain and the JSON renderer."""
    record = _record(
        "Application %s sent by %s",
        42,
        "sara@example.com",
        status_code="200",
        duration_ms="12.5",
        user_id="7",
    )

    line = benchmark(formatter.format, record)

    data = json.loads(line)
    assert "sara@example.com" not in line
    assert data["event"].startswith("Application 42 sent by sha256:")
    assert data["status_code"] == 200


@pytest.mark.benchmark(group="logging")
def test_bench_redact_nested_payload(benchmark):
    """Redaction is the costliest processor: it walks every value with two regexes."""
    payload = {
        "event": "payment for card 4111 1111 1111 1111 by sara@example.com",
        "password": "hunter2",
        "form": {"email": "sara@example.com", "notes": ["call 555", "ok"] * 10},
    }

    result = benchmark(lambda: logging_config.redact(None, "info", dict(payload)))

    assert result["password"] == logging_config.REDACTED
    assert "4111" not in result["event"]
