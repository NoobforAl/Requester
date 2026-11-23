"""Django settings for the Requester project.

Everything environment specific is read from environment variables.
With no database variables set the project falls back to SQLite, a local-memory
cache and eager Celery tasks, so `make dev` works without any service running.
"""

import importlib.util
import os
from pathlib import Path

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

from observability.logging_config import build_logging, configure_structlog

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [
        item.strip()
        for item in os.environ.get(name, default).split(",")
        if item.strip()
    ]


# Production-safe default: debug is OFF unless explicitly enabled.
DEBUG = env_bool("DJANGO_DEBUG", default=False)

SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "The SECRET_KEY environment variable is required when DJANGO_DEBUG is off."
        )
    SECRET_KEY = "insecure-development-key-do-not-use-in-production"  # noqa: S105

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]" if DEBUG else "")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Email
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "no-reply@requester.local")
# Absolute base of the links placed in e-mails (job alerts).
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")
# Django 6.1 replaced the EMAIL_* settings with MAILERS. Without EMAIL_HOST mail
# is printed to the console, which is what you want in development.
if os.environ.get("EMAIL_HOST"):
    MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "OPTIONS": {
                "host": os.environ["EMAIL_HOST"],
                "port": int(os.environ.get("EMAIL_PORT") or 25),
                "username": os.environ.get("EMAIL_HOST_USER", ""),
                "password": os.environ.get("EMAIL_HOST_PASSWORD", ""),
                "use_tls": env_bool("EMAIL_USE_TLS", default=True),
            },
        }
    }
else:
    MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}

# MariaDB cannot build the Lower(email) unique constraints (models.W044). That is
# fine there: its default collations are case-insensitive, so the plain unique
# index already rejects "A@x.com" next to "a@x.com". SQLite (dev/tests) enforces
# them through the constraints.
SILENCED_SYSTEM_CHECKS = ["models.W044"]

# Database: MariaDB (via the MySQL backend) when DB_NAME is set, SQLite otherwise.
if os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ.get("DB_USER", ""),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", ""),
            "PORT": os.environ.get("DB_PORT", ""),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {"charset": "utf8mb4"},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
        }
    }

# Elasticsearch: only synced when a URL is configured.
ELASTICSEARCH_URL = os.environ.get("ELASTICSEARCH_URL", "")
_es_default: dict[str, object] = {"hosts": ELASTICSEARCH_URL}
if os.environ.get("ELASTICSEARCH_USERNAME"):
    _es_default["basic_auth"] = (
        os.environ["ELASTICSEARCH_USERNAME"],
        os.environ.get("ELASTICSEARCH_PASSWORD", ""),
    )
ELASTICSEARCH_DSL = {"default": _es_default}
ELASTICSEARCH_DSL_AUTOSYNC = bool(ELASTICSEARCH_URL)
ELASTICSEARCH_DSL_SIGNAL_PROCESSOR = (
    "django_elasticsearch_dsl.signals.RealTimeSignalProcessor"
)

# Cache: Redis when configured, local memory otherwise.
REDIS_URL = os.environ.get("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Celery (read with the CELERY_ namespace, see requester/celery.py)
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND") or None
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
# Without a broker (local dev, tests) run tasks inline instead of failing.
CELERY_TASK_ALWAYS_EAGER = not CELERY_BROKER_URL
CELERY_TASK_EAGER_PROPAGATES = False
# Keep Django's LOGGING (JSON) in workers instead of Celery's own handlers.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
# Task events for celery-exporter (the worker also runs with -E).
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True

# Celery beat: job-alert digests. Run with `celery -A requester beat` (the compose
# `scheduler` service). Times are CELERY_TIMEZONE (UTC); 04:30 UTC = 08:00 Tehran.
CELERY_BEAT_SCHEDULE = {
    "job-alerts-daily": {
        "task": "applications.tasks.send_job_alerts",
        "schedule": crontab(hour=4, minute=30),
        "args": ("daily",),
    },
    "job-alerts-weekly": {
        "task": "applications.tasks.send_job_alerts",
        "schedule": crontab(hour=4, minute=30, day_of_week="mon"),
        "args": ("weekly",),
    },
}

# AI resume summaries through OpenRouter: on when OPENROUTER_API_KEY is set, skipped
# otherwise. Enabling it sends the text of uploaded resumes to that third party.
AI_TIMEOUT_SECONDS = int(os.environ.get("AI_TIMEOUT_SECONDS") or 120)
AI_MAX_INPUT_CHARS = int(os.environ.get("AI_MAX_INPUT_CHARS", "12000"))
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemma-3-4b-it")
OPENROUTER_BASE_URL = os.environ.get(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")

# Logging: structlog, one JSON object per line on stdout (see docs/log-schema.md).
# LOG_FORMAT=console gives human-readable lines; it is the default with DEBUG on.
LOG_LEVEL = (os.environ.get("LOG_LEVEL") or "INFO").upper()
LOG_FORMAT = os.environ.get("LOG_FORMAT") or ("console" if DEBUG else "json")
configure_structlog(LOG_LEVEL, LOG_FORMAT)
LOGGING = build_logging(LOG_LEVEL, LOG_FORMAT)
# RequestLogMiddleware already logs every request (with the route template, not the
# raw URL). Keep django.request for 5xx only, so 4xx lines are not duplicated and
# raw paths (e.g. signed unsubscribe tokens) are not logged for 404s.
LOGGING["loggers"]["django.request"]["level"] = "ERROR"
# runserver writes its own access line per request; http_request already covers it.
LOGGING["loggers"]["django.server"]["level"] = "WARNING"

INSTALLED_APPS = [
    "employers",
    "candidates",
    "applications",
    "django_extensions",
    "django_elasticsearch_dsl",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Request ID + one structured `http_request` log line per request.
    "observability.middleware.RequestLogMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Metrics (django-prometheus). /metrics is served only with PROMETHEUS_ENABLED and
# answers 404 unless the request carries `Authorization: Bearer $METRICS_TOKEN`.
# An empty PROMETHEUS_MULTIPROC_DIR must not count as set: prometheus_client only
# checks that the key exists and would then fail on every scrape.
if not os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    os.environ.pop("PROMETHEUS_MULTIPROC_DIR", None)
PROMETHEUS_ENABLED = env_bool("PROMETHEUS_ENABLED")
METRICS_TOKEN = os.environ.get("METRICS_TOKEN", "")
METRICS_ALLOWED_IPS = env_list("METRICS_ALLOWED_IPS")
if PROMETHEUS_ENABLED:
    INSTALLED_APPS.append("django_prometheus")
    MIDDLEWARE = [
        "django_prometheus.middleware.PrometheusBeforeMiddleware",
        *MIDDLEWARE,
        "django_prometheus.middleware.PrometheusAfterMiddleware",
    ]
    _db_engines = {
        "django.db.backends.mysql": "django_prometheus.db.backends.mysql",
        "django.db.backends.sqlite3": "django_prometheus.db.backends.sqlite3",
    }
    _engine = str(DATABASES["default"]["ENGINE"])
    DATABASES["default"]["ENGINE"] = _db_engines.get(_engine, _engine)
    if CACHES["default"]["BACKEND"] == "django.core.cache.backends.locmem.LocMemCache":
        CACHES["default"]["BACKEND"] = (
            "django_prometheus.cache.backends.locmem.LocMemCache"
        )
    # The Redis cache stays on Django's RedisCache: the django-prometheus Redis
    # wrapper needs django-redis. Redis numbers come from redis-exporter.

# Dev-only profilers: on only with DEBUG *and* the env flag *and* the package
# installed (the production image is built without the dev group, so never there).
DEBUG_TOOLBAR = (
    DEBUG
    and env_bool("DEBUG_TOOLBAR")
    and importlib.util.find_spec("debug_toolbar") is not None
)
SILK_ENABLED = (
    DEBUG and env_bool("SILK_ENABLED") and importlib.util.find_spec("silk") is not None
)
if DEBUG_TOOLBAR:
    INSTALLED_APPS.append("debug_toolbar")
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.middleware.common.CommonMiddleware"),
        "debug_toolbar.middleware.DebugToolbarMiddleware",
    )
    INTERNAL_IPS = ["127.0.0.1", "::1"]
if SILK_ENABLED:
    # Silk stores profiles in its own tables: run `migrate` after turning it on.
    INSTALLED_APPS.append("silk")
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        "silk.middleware.SilkyMiddleware",
    )
    SILKY_PYTHON_PROFILER = False
    SILKY_AUTHENTICATION = True
    SILKY_AUTHORISATION = True  # staff only

ROOT_URLCONF = "requester.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "requester.context_processors.languages",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "requester.wsgi.application"
ASGI_APPLICATION = "requester.asgi.application"

_PASSWORD_VALIDATORS = (
    "UserAttributeSimilarityValidator",
    "MinimumLengthValidator",
    "CommonPasswordValidator",
    "NumericPasswordValidator",
)
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in _PASSWORD_VALIDATORS
]

# Persian is the default; the language is chosen per visitor (cookie/session) with
# the switcher in the page header, so URLs do not carry a language prefix.
LANGUAGE_CODE = "fa"
LANGUAGES = [
    ("fa", "فارسی"),
    ("en", "English"),
    ("ar", "العربية"),
    ("de", "Deutsch"),
    ("fr", "Français"),
    ("ru", "Русский"),
    ("zh-hans", "简体中文"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# Static files: sources live in src/static, collectstatic writes to src/staticfiles.
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

# Uploaded resumes live in src/resumes/ (same place as before). They are never
# served by URL; the employer-only view streams them after an ownership check.
MEDIA_ROOT = BASE_DIR

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Each portal sends anonymous visitors to its own login page; this is the fallback.
LOGIN_URL = "/"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# Resume upload limits
RESUME_MAX_UPLOAD_BYTES = 5 * 1024 * 1024

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("SECURE_COOKIES", default=True)
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", default=False)
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    if env_bool("BEHIND_PROXY"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Error reporting: off while SENTRY_DSN is empty (see observability/sentry.py).
from observability.sentry import setup_sentry  # noqa: E402

setup_sentry()
