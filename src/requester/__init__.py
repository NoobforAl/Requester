"""The Django project package: settings, URLs, entry points and the shared pieces.

``requester`` is the project, not an installed app (it is not in INSTALLED_APPS and
has no models). It wires the apps together and holds what both portals share.

Modules
    settings.py, settings_test.py, settings_mariadb_test.py   configuration from
        environment variables; the test settings run on SQLite, the MariaDB ones
        against the compose database.
    urls.py       root routes; mounts ``candidates.urls`` and ``employers.urls``,
                  the admin, the language switch, ``/metrics`` and the old-URL
                  redirects.
    portal.py     login, register, logout and the access mixin used by both portals.
    forms.py      shared form helpers (Jinja2 widgets).
    localdates.py Jalali versus Gregorian dates by active language.
    context_processors.py   language list for templates.
    celery.py     the Celery app (see below); runtime.py sizes worker pools from
                  the container's CPU quota.
    admin.py, unfold_admin.py   admin theme callbacks and the Unfold fixes.
    wsgi.py, asgi.py   entry points; they start OpenTelemetry tracing.

Depends on (this package imports)
    observability.*   settings (logging, sentry), wsgi/asgi (tracing), celery
                      (signals, tracing), urls (metrics)
    employers.models, applications.models   admin.py only (sidebar badges)
    Django, Celery, Unfold and the rest of the stack.

Used by (imports this package)
    candidates, employers     portal, forms, localdates, unfold_admin
    gunicorn, Celery, manage.py, pytest   settings and entry points

Import-time behaviour (the only code in this file)
    Importing ``requester`` loads the Celery app, so ``@shared_task`` and ``.delay()``
    use our broker settings in every process. ``celery.py`` only sets
    ``DJANGO_SETTINGS_MODULE`` and creates the app; it must not import models, which
    Django has not loaded yet at this point. Keep anything else out of this file.
"""

# Load the Celery app with Django so `.delay()` uses our broker settings.
from .celery import app as celery_app

__all__ = ("celery_app",)
