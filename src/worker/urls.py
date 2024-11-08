from django.urls import path
from worker import views

urlpatterns = [
    path("", views.Dashboard.as_view(), name="worker_dashboard"),
    path("login/", views.Login.as_view(), name="worker_login"),
    path("logout/", views.Logout.as_view(), name="worker_logout"),
    path("register/", views.Register.as_view(), name="worker_register"),

    path("settings/", views.Settings.as_view(), name="worker_settings"),

    path("jobs/", views.Jobs.as_view(), name="worker_jobs"),
    path("jobs/<int:pk>/", views.Jobs.as_view(), name="worker_pick_jobs"),
]
