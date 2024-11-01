from django.contrib import admin
from django.urls import path, include

from requester.views import mainPage, handler404

# handler404 = handler404
_ = handler404

urlpatterns = [
    path("", mainPage),
    path("admin/", admin.site.urls),
    # path("worker/", include("worker.urls")),
    path("offer/", include("offer.urls")),
]
