from django.urls import path
from worker import views

urlpatterns = [
    path("register/", views.Register.as_view(), name="register"),
    path("login/", views.Login.as_view(), name="login"),
    path("logout/", views.Logout.as_view(), name="logout"),
    path("jobs/", views.Jobs.as_view(), name="jobs"),
    path("jobs/<int:pk>/", views.Jobs.as_view(), name="jobs"),
    path("", views.Dashbord.as_view(), name="dashbord"),
    path("info/", views.Info.as_view(), name="info"),  # change information!
]
