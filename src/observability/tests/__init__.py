"""Tests of the observability package, roughly one file per module.

    test_logging.py   JSON fields, redaction and e-mail hashing, request line,
                      Celery request-ID propagation.
    test_metrics.py   the Prometheus endpoint and its protection.
    test_sentry.py    off without a DSN, ``before_send`` scrubbing, event tags.
    test_tracing.py   off by default, sampler, idempotent setup, trace ID in logs.

Depends on: observability.* only (plus pytest and Django's test client). Logging and
tracing are process-wide, so the tests snapshot and restore their state
(``_snapshot_logging``/``_restore_logging`` in test_logging.py); reuse them in new
tests.
"""
