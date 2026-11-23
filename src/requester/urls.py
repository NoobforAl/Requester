from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from django.views.i18n import set_language

import requester.admin  # noqa: F401 - admin theme callbacks, auth models in Unfold
from observability.metrics import metrics_view
from requester.views import home

handler404 = "requester.views.handler404"

urlpatterns = [
    path("", home, name="home"),
    path("admin/", admin.site.urls),
    # POST-only language switcher (cookie + session); see the header dropdown.
    path("i18n/set-language/", set_language, name="set_language"),
    path("candidates/", include("candidates.urls")),
    path("employers/", include("employers.urls")),
    # Old URLs from before the rename keep working.
    path(
        "worker/<path:rest>",
        RedirectView.as_view(url="/candidates/%(rest)s", permanent=True),
    ),
    path("worker/", RedirectView.as_view(url="/candidates/", permanent=True)),
    path(
        "offer/<path:rest>",
        RedirectView.as_view(url="/employers/%(rest)s", permanent=True),
    ),
    path("offer/", RedirectView.as_view(url="/employers/", permanent=True)),
]

if settings.PROMETHEUS_ENABLED:
    # Token-protected (404 otherwise); scraped by Prometheus on the internal network.
    urlpatterns.append(path("metrics", metrics_view, name="prometheus-metrics"))

# Dev-only profilers (see settings: DEBUG plus an env flag).
if getattr(settings, "DEBUG_TOOLBAR", False):
    urlpatterns.append(path("__debug__/", include("debug_toolbar.urls")))
if getattr(settings, "SILK_ENABLED", False):
    urlpatterns.append(path("silk/", include("silk.urls", namespace="silk")))
