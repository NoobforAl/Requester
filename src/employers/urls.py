from django.urls import path

from employers import views

urlpatterns = [
    path("", views.Dashboard.as_view(), name="employer_dashboard"),
    path("login/", views.Login.as_view(), name="employer_login"),
    path("logout/", views.Logout.as_view(), name="employer_logout"),
    path("register/", views.Register.as_view(), name="employer_register"),
    path("settings/", views.Settings.as_view(), name="employer_settings"),
    path("jobs/", views.Postings.as_view(), name="employer_jobs"),
    path("jobs/<int:pk>/", views.PostingDetail.as_view(), name="employer_job"),
    path("jobs/<int:pk>/edit/", views.PostingEdit.as_view(), name="employer_job_edit"),
    path(
        "jobs/<int:pk>/toggle/",
        views.PostingToggle.as_view(),
        name="employer_job_toggle",
    ),
    path(
        "jobs/<int:pk>/delete/",
        views.PostingDelete.as_view(),
        name="employer_job_delete",
    ),
    path(
        "jobs/<int:pk>/report/",
        views.PostingReport.as_view(),
        name="employer_job_report",
    ),
    path("resume/<int:pk>/", views.ResumeDownload.as_view(), name="employer_resume"),
    path(
        "applications/<int:pk>/status/",
        views.ApplicationStatusUpdate.as_view(),
        name="employer_application_status",
    ),
]
