"""Admin site look and navigation (django-unfold), configured in Python only.

The theme itself is the ``UNFOLD`` setting (settings.py); this module holds the
callbacks it points at, and the auth models re-registered with Unfold's forms
(the stock ``UserAdmin`` would render unstyled). Imported from ``urls.py``,
because ``requester`` is the project package, not an installed app.
"""

import os

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.http import HttpRequest
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from applications.models import Application
from employers.models import JobPosting
from requester.unfold_admin import ModelAdmin

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
# Unfold documents this pairing; the stubs disagree on get_form's signature.
class UserAdmin(  # pyright: ignore[reportIncompatibleMethodOverride]
    BaseUserAdmin, ModelAdmin
):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass


#: APP_ENVIRONMENT -> badge color in the admin header, so nobody edits production
#: thinking it is a test site.
ENVIRONMENT_COLORS = {
    "production": "danger",
    "staging": "warning",
    "perf": "info",
    "development": "success",
}


def environment_callback(request: HttpRequest) -> list[str]:
    environment = os.environ.get("APP_ENVIRONMENT") or "development"
    return [environment.title(), ENVIRONMENT_COLORS.get(environment, "info")]


# Sidebar badges: small live counts next to a menu entry (one COUNT each).
def open_postings_badge(request: HttpRequest) -> int:
    return JobPosting.objects.open().count()


def pending_applications_badge(request: HttpRequest) -> int:
    return Application.objects.filter(status=Application.Status.PENDING).count()
