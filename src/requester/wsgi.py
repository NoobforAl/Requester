"""
WSGI config for requester project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

from observability.tracing import setup_tracing

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "requester.settings")

# Tracing must start before the app loads MIDDLEWARE. gunicorn forks workers before
# importing this module (no --preload), so each worker gets its own exporter.
# celery=True makes task publishing carry the trace context to the worker.
setup_tracing(celery=True)

application = get_wsgi_application()
