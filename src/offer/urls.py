from django.urls import path

from offer import views

urlpatterns = [
    path("", views.Dashboard.as_view(), name="offer_dashboard"),

    path("login/", views.Login.as_view(), name="offer_login"),
    path("logout/", views.Logout.as_view(), name="offer_logout"),
    path("register/", views.Register.as_view(), name="offer_register"),

    path("settings/", views.Settings.as_view(), name="offer_settings"),

    path("jobs/", views.Jobs.as_view(), name="offer_jobs"),
    path("jobs/<int:pk>/", views.Jobs.as_view(), name="offer_job"),

    # path download resume
    path("resume/<int:pk>/", views.Resume.as_view(), name="download_resume"),

    # path for change status of request of resume
    path(
        "resume/<int:pk>/status/",
        views.ResumeStatus.as_view(),
        name="resume_status"
    ),
]
