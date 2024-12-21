from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

from requester.views import mainPage, handler404

# handler404 = handler404
handler404 = handler404

urlpatterns = []

if settings.DEBUG:
    urlpatterns += static(
        settings.STATIC_URL,
        document_root=settings.STATIC_ROOT
    )


urlpatterns += [
    path("", mainPage),
    path("admin/", admin.site.urls),
    path("worker/", include("worker.urls")),
    path("offer/", include("offer.urls")),
]
