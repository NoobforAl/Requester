import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "requester.settings")

app = Celery("requester")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()

# request_id propagation over task headers; keep Django's LOGGING in workers.
from celery.signals import beat_init, worker_process_init  # noqa: E402

import observability.celery_signals  # noqa: E402, F401


@worker_process_init.connect
def _init_worker_process(**_kwargs):
    """Runs in every prefork child, after the fork."""
    from observability.sentry import setup_sentry  # noqa: PLC0415
    from observability.tracing import setup_tracing  # noqa: PLC0415

    setup_tracing(celery=True)
    setup_sentry()  # no-op if settings already initialised it for this DSN


@beat_init.connect
def _init_beat(**_kwargs):
    from observability.tracing import setup_tracing  # noqa: PLC0415

    setup_tracing(celery=True)
