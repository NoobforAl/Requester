"""OpenTelemetry tracing: OTLP/HTTP export to the collector, then Jaeger.

Off unless ``OTEL_ENABLED`` is true. :func:`setup_tracing` is idempotent and never
raises: a failure logs ``tracing_setup_failed`` and the app runs untraced.

Where it is called, and why that is fork-safe:

* **gunicorn** (sync workers, no ``--preload``): the master forks the workers
  *before* any of them imports ``requester/wsgi.py``. ``wsgi.py`` calls
  ``setup_tracing()`` before ``get_wsgi_application()``, so every worker builds
  its own provider, exporter thread and HTTP session after the fork, and the
  Django middleware is inserted before the WSGI handler loads ``MIDDLEWARE``.
  (With ``--preload`` this would have to move into a ``post_fork`` hook.)
* **Celery** (prefork pool): the main worker process forks its pool children,
  so tracing is set up in ``worker_process_init``, which runs in each child.
  Beat has no pool and calls it from ``beat_init``. With the ``solo``/``threads``
  pools use ``worker_init`` instead (``worker_process_init`` is not sent).
* **runserver/ASGI**: call it before the application is created.

Configuration (environment):

* ``SERVICE_NAME`` (``web``), ``APP_VERSION`` (``0.1.0``) and ``APP_ENVIRONMENT``
  (``development``) become the ``service.name``, ``service.version`` and
  ``deployment.environment.name`` resource attributes.
* Sampling: ``ParentBased(TraceIdRatioBased(OTEL_TRACES_SAMPLER_ARG))``, ratio
  0.1 by default. An incoming W3C ``traceparent`` decides for its trace. When the
  standard ``OTEL_TRACES_SAMPLER`` is set, the SDK's own env handling is used
  instead (for example ``always_on`` or ``parentbased_always_off``).
* ``OTEL_EXPORTER_OTLP_ENDPOINT`` (``http://otel-collector:4318``): the OTLP/HTTP
  exporter appends ``/v1/traces`` itself.
* ``OTEL_PYTHON_DJANGO_EXCLUDED_URLS`` (or ``OTEL_PYTHON_EXCLUDED_URLS``):
  comma-separated regexes searched in the full URL. When neither is set,
  :data:`DEFAULT_EXCLUDED_URLS` keeps ``/metrics`` scrapes and static files out.

Instrumented: Django (server spans with ``http.route``), mysqlclient, redis,
httpx and, with ``celery=True``, Celery (publish and run spans; the trace context
travels in the task headers). Instrumentors get the provider explicitly, so the
tests can run without touching the global provider.
"""

from __future__ import annotations

import os
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.sampling import (
    ParentBased,
    Sampler,
    TraceIdRatioBased,
)

logger = structlog.get_logger(__name__)

DEFAULT_SAMPLE_RATIO = 0.1
DEFAULT_EXCLUDED_URLS = r"/metrics/?$,/static/,/favicon\.ico$"
_TRUE = {"1", "true", "yes", "on"}

# Module state: the active provider and what we instrumented (for shutdown).
_provider: TracerProvider | None = None
_instrumentors: list[Any] = []
_celery_instrumented = False


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


def tracing_enabled() -> bool:
    return _env_bool("OTEL_ENABLED")


def sample_ratio() -> float:
    """``OTEL_TRACES_SAMPLER_ARG`` as a ratio in [0, 1] (0.1 when unset/invalid)."""
    raw = os.environ.get("OTEL_TRACES_SAMPLER_ARG", "").strip()
    try:
        ratio = float(raw) if raw else DEFAULT_SAMPLE_RATIO
    except ValueError:
        ratio = DEFAULT_SAMPLE_RATIO
    return min(max(ratio, 0.0), 1.0)


def build_sampler() -> Sampler | None:
    """Parent-based ratio sampler, or ``None`` to let the SDK read the env."""
    if os.environ.get("OTEL_TRACES_SAMPLER", "").strip():
        return None
    return ParentBased(TraceIdRatioBased(sample_ratio()))


def build_resource() -> Resource:
    return Resource.create(
        {
            "service.name": os.environ.get("SERVICE_NAME") or "web",
            "service.version": os.environ.get("APP_VERSION") or "0.1.0",
            "deployment.environment.name": (
                os.environ.get("APP_ENVIRONMENT") or "development"
            ),
        }
    )


def build_provider(exporter: SpanExporter | None = None) -> TracerProvider:
    """A provider with our resource and sampler.

    Without ``exporter`` spans go in batches to the OTLP/HTTP exporter. An injected
    exporter (tests) gets a synchronous ``SimpleSpanProcessor``.
    """
    provider = TracerProvider(resource=build_resource(), sampler=build_sampler())
    if exporter is None:
        from opentelemetry.exporter.otlp.proto.http import (  # noqa: PLC0415
            trace_exporter,
        )

        provider.add_span_processor(
            BatchSpanProcessor(trace_exporter.OTLPSpanExporter())
        )
    else:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def _django_kwargs() -> dict[str, Any]:
    env_set = os.environ.get("OTEL_PYTHON_DJANGO_EXCLUDED_URLS") or os.environ.get(
        "OTEL_PYTHON_EXCLUDED_URLS"
    )
    # None makes the instrumentor read the env variables itself.
    return {} if env_set else {"excluded_urls": DEFAULT_EXCLUDED_URLS}


def _instrument(instrumentor: Any, provider: TracerProvider, **kwargs: Any) -> None:
    if instrumentor.is_instrumented_by_opentelemetry:
        return
    instrumentor.instrument(tracer_provider=provider, **kwargs)
    _instrumentors.append(instrumentor)


def _instrument_celery(provider: TracerProvider) -> None:
    global _celery_instrumented  # noqa: PLW0603
    from opentelemetry.instrumentation.celery import CeleryInstrumentor  # noqa: PLC0415

    _instrument(CeleryInstrumentor(), provider)
    _celery_instrumented = True


def setup_tracing(
    *,
    celery: bool = False,
    exporter: SpanExporter | None = None,
    set_global: bool = True,
) -> bool:
    """Set up tracing once per process; True when tracing is active.

    ``exporter`` and ``set_global=False`` exist for tests: they keep spans in
    memory and leave the global OTel provider (which can only be set once) alone.
    """
    global _provider  # noqa: PLW0603
    if not tracing_enabled():
        return False
    try:
        if _provider is not None:  # already set up: maybe add Celery
            if celery and not _celery_instrumented:
                _instrument_celery(_provider)
            return True

        from opentelemetry.instrumentation.django import (  # noqa: PLC0415
            DjangoInstrumentor,
        )
        from opentelemetry.instrumentation.httpx import (  # noqa: PLC0415
            HTTPXClientInstrumentor,
        )
        from opentelemetry.instrumentation.mysqlclient import (  # noqa: PLC0415
            MySQLClientInstrumentor,
        )
        from opentelemetry.instrumentation.redis import (  # noqa: PLC0415
            RedisInstrumentor,
        )

        provider = build_provider(exporter)
        _instrument(DjangoInstrumentor(), provider, **_django_kwargs())
        _instrument(MySQLClientInstrumentor(), provider)
        _instrument(RedisInstrumentor(), provider)
        _instrument(HTTPXClientInstrumentor(), provider)
        if celery:
            _instrument_celery(provider)
        if set_global:
            trace.set_tracer_provider(provider)
        _provider = provider
    except Exception:  # never take the app down because of tracing
        logger.exception("tracing_setup_failed")
        shutdown_tracing()
        return False
    logger.info(
        "tracing_enabled",
        sampler=str(provider.sampler.get_description()),
        celery=celery,
    )
    return True


def get_provider() -> TracerProvider | None:
    return _provider


def shutdown_tracing() -> None:
    """Uninstrument everything and flush/stop the provider (tests, shutdown).

    The global provider, if one was set, stays registered: OTel allows that only
    once per process.
    """
    global _provider, _celery_instrumented  # noqa: PLW0603
    while _instrumentors:
        instrumentor = _instrumentors.pop()
        try:
            instrumentor.uninstrument()
        except Exception:  # pragma: no cover - best effort
            logger.exception("tracing_uninstrument_failed")
    _celery_instrumented = False
    provider, _provider = _provider, None
    if provider is not None:
        provider.shutdown()
