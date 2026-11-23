"""Settings used by pytest and the mypy Django plugin (no services required)."""

import os
import tempfile
from pathlib import Path

os.environ["DJANGO_DEBUG"] = "true"
for _name in (
    "DB_NAME",
    "REDIS_URL",
    "CELERY_BROKER_URL",
    "OPENROUTER_API_KEY",
    # Observability and dev tools stay off in tests whatever the shell has set.
    "DEBUG_TOOLBAR",
    "SILK_ENABLED",
    "PROMETHEUS_ENABLED",
    "PROMETHEUS_MULTIPROC_DIR",
    "OTEL_ENABLED",
    "OTEL_TRACES_SAMPLER",
    "SENTRY_DSN",
):
    os.environ.pop(_name, None)

from .settings import *  # noqa: E402, F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="requester-test-media-"))
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Off by default so a test that lists, changes and lists again sees the change; the
# cache's own tests turn it on.
JOB_SEARCH_CACHE_SECONDS = 0
