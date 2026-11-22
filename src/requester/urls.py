from django.contrib import admin
from django.urls import include, path

from requester.views import mainPage

handler404 = "requester.views.handler404"

urlpatterns = [
    path("", mainPage, name="home"),
    path("admin/", admin.site.urls),
    path("worker/", include("worker.urls")),
    path("offer/", include("offer.urls")),
]
