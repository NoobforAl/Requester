"""Observability: structured logs, request IDs, metrics, tracing, error reports.

A plain package (no models), so it is not in INSTALLED_APPS. Each module can be
imported on its own; nothing is re-exported here, so importing ``observability`` is
free and callers import the module they need (``observability.tracing`` ...).
Operations guide: docs/observability.md; log fields: docs/log-schema.md.

Modules
    logging_config.py  structlog on top of stdlib ``logging``: JSON or console lines,
                       ``LOGGING`` dict for Django and Celery (``build_logging``,
                       ``configure_structlog``). Reads ``LOG_LEVEL``, ``LOG_FORMAT``.
    middleware.py      ``RequestLogMiddleware``: request ID in, one ``http_request``
                       log line out per request; listed in MIDDLEWARE (settings.py).
    celery_signals.py  copies the request ID into task headers and binds it (plus
                       task id and name) around each task; connected by importing the
                       module (requester/celery.py).
    metrics.py         ``metrics_view``: token-protected Prometheus export, plus the
                       gunicorn multiprocess helpers (gunicorn.conf.py).
    tracing.py         OpenTelemetry setup (OTLP/HTTP to the collector, then Jaeger);
                       ``setup_tracing`` is called from wsgi, asgi and Celery hooks.
    sentry.py          Sentry error reports; off while ``SENTRY_DSN`` is empty.

Depends on (this package imports)
    No other project package. Only Django settings and third parties: structlog,
    sentry-sdk, opentelemetry-*, prometheus_client, django-prometheus, Celery.

Used by (imports this package)
    requester.settings   logging_config, sentry
    requester.wsgi, requester.asgi   tracing
    requester.celery     celery_signals, tracing, sentry (inside worker hooks)
    requester.urls       metrics
    gunicorn.conf.py     metrics helpers

Rules
    * Never import ``employers``, ``candidates``, ``applications`` or ``requester``
      here: ``requester.settings`` imports this package while settings are still
      loading, so a back-import is circular.
    * Start-up order matters: settings call ``configure_structlog`` and
      ``setup_sentry`` first, tracing starts per process (after the gunicorn or
      Celery fork), and ``celery_signals`` is imported by ``requester/celery.py``.
"""
