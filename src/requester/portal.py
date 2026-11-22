"""Shared building blocks for the two portals (``candidate`` and ``employer``).

Both portals have the same login, logout and registration flow and the same rule:
a signed-in user may only use the portal their account belongs to. The user's
profile is the one-to-one object reachable as ``user.candidate`` or ``user.employer``.
URL names follow the pattern ``<portal>_login`` / ``<portal>_dashboard``.
"""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.http.response import HttpResponseBase
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View

NO_ACCESS_MESSAGE = _(
    "You do not have access to this area. Sign in with an account of this area."
)


class AuthenticatedRequest(HttpRequest):
    """Request of a signed-in user; use it in views behind ``PortalAccessMixin``."""

    user: User


def has_profile(user, portal: str) -> bool:
    """True when the signed-in user owns a profile for this portal."""
    return user.is_authenticated and hasattr(user, portal)


class PortalAccessMixin(LoginRequiredMixin):
    """Only signed-in users that own a profile for ``portal`` get through."""

    portal: str = ""

    def get_login_url(self) -> str:
        return reverse(f"{self.portal}_login")

    def dispatch(self, request: HttpRequest, *args, **kwargs) -> HttpResponseBase:
        if request.user.is_authenticated and not has_profile(request.user, self.portal):
            messages.error(request, NO_ACCESS_MESSAGE)
            return redirect(self.get_login_url())
        return super().dispatch(request, *args, **kwargs)


class PortalLoginView(View):
    portal: str = ""
    template_name: str = ""
    form_class: type

    def get(self, req: HttpRequest) -> HttpResponse:
        if has_profile(req.user, self.portal):
            return redirect(f"{self.portal}_dashboard")
        return render(req, self.template_name, {"form": self.form_class()})

    def post(self, req: HttpRequest) -> HttpResponse:
        if has_profile(req.user, self.portal):
            return redirect(f"{self.portal}_dashboard")

        form = self.form_class(request=req, data=req.POST)
        if not form.is_valid():
            messages.error(req, _("Wrong username or password. Try again."))
            return redirect(f"{self.portal}_login")

        user = form.get_user()
        if not has_profile(user, self.portal):
            messages.error(req, NO_ACCESS_MESSAGE)
            return redirect(f"{self.portal}_login")

        login(req, user)
        return redirect(f"{self.portal}_dashboard")


class PortalLogoutView(View):
    """Logging out changes state, so it is POST-only (no CSRF logout via a link)."""

    portal: str = ""

    def post(self, req: HttpRequest) -> HttpResponse:
        logout(req)
        return redirect(f"{self.portal}_login")


class PortalRegisterView(View):
    portal: str = ""
    template_name: str = ""
    form_class: type

    def get(self, req: HttpRequest) -> HttpResponse:
        if has_profile(req.user, self.portal):
            return redirect(f"{self.portal}_dashboard")
        return render(req, self.template_name, {"form": self.form_class()})

    def post(self, req: HttpRequest) -> HttpResponse:
        if has_profile(req.user, self.portal):
            return redirect(f"{self.portal}_dashboard")

        form = self.form_class(req.POST)
        if form.is_valid():
            form.save()
            messages.success(req, _("You are registered. Sign in now."))
            return redirect(f"{self.portal}_login")

        messages.error(req, _("Registration failed. Fix the form errors."))
        return render(req, self.template_name, {"form": form})
