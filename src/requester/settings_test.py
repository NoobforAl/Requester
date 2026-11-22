"""Settings used by pytest and the mypy Django plugin (no services required)."""

import os
import tempfile
from pathlib import Path

os.environ["DJANGO_DEBUG"] = "true"
for _name in (
    "DB_NAME",
    "REDIS_URL",
    "ELASTICSEARCH_URL",
    "CELERY_BROKER_URL",
    "LLAMA_SERVER_URL",
    "OPENROUTER_API_KEY",
    "AI_PROVIDER",
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
