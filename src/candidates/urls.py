from django.urls import path

from candidates import views

urlpatterns = [
    path("", views.Dashboard.as_view(), name="candidate_dashboard"),
    path("login/", views.Login.as_view(), name="candidate_login"),
    path("logout/", views.Logout.as_view(), name="candidate_logout"),
    path("register/", views.Register.as_view(), name="candidate_register"),
    path("settings/", views.Settings.as_view(), name="candidate_settings"),
    path("jobs/", views.Postings.as_view(), name="candidate_jobs"),
    path("jobs/<int:pk>/", views.Postings.as_view(), name="candidate_job"),
    path("jobs/<int:pk>/save/", views.PostingSave.as_view(), name="candidate_job_save"),
    path("saved/", views.SavedPostings.as_view(), name="candidate_saved"),
    path("applications/", views.Applications.as_view(), name="candidate_applications"),
    path(
        "applications/<int:pk>/withdraw/",
        views.ApplicationWithdraw.as_view(),
        name="candidate_application_withdraw",
    ),
    path("alerts/", views.Alerts.as_view(), name="candidate_alerts"),
    path(
        "alerts/<int:pk>/toggle/",
        views.AlertToggle.as_view(),
        name="candidate_alert_toggle",
    ),
    path(
        "alerts/<int:pk>/delete/",
        views.AlertDelete.as_view(),
        name="candidate_alert_delete",
    ),
    path(
        "alerts/unsubscribe/<str:token>/",
        views.AlertUnsubscribe.as_view(),
        name="candidate_alert_unsubscribe",
    ),
]
