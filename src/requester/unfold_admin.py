"""Fixes for two things Unfold 0.110 gets wrong on Django 6.1.

* ``ModelAdmin``: Unfold overrides ``get_action_choices(request, default_choices)``.
  Django 6.1 deprecates that signature (it must accept ``action_location``) and warns
  on every changelist render (``RemovedInDjango2028Warning``).
* ``RangeDateTimeFilter``: Unfold filters with naive datetimes, so Django warns and the
  range is read in UTC instead of the active time zone.

Admin classes import both from here instead of ``unfold``; drop this module once
Unfold fixes them.
"""

from django.contrib import admin
from django.contrib.admin.options import ActionLocation
from django.core.exceptions import ValidationError
from django.core.validators import EMPTY_VALUES
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.contrib.filters.admin import (
    RangeDateTimeFilter as UnfoldRangeDateTimeFilter,
)
from unfold.utils import parse_datetime_str


class ModelAdmin(UnfoldModelAdmin):
    def get_action_choices(
        self,
        request: HttpRequest,
        default_choices: list[tuple[str, str]] | None = None,
        action_location: ActionLocation = ActionLocation.CHANGE_LIST,
    ) -> list[tuple[str, str]]:
        # Unfold's body, minus its super() call that drops action_location.
        return admin.ModelAdmin.get_action_choices(
            self, request, [("", str(_("Select action")))], action_location
        )


class RangeDateTimeFilter(UnfoldRangeDateTimeFilter):
    def queryset(self, request: HttpRequest, queryset: QuerySet) -> QuerySet | None:
        filters = {}
        for side, lookup in (("from", "gte"), ("to", "lte")):
            day = self.used_parameters.get(f"{self.parameter_name}_{side}_0")
            time = self.used_parameters.get(f"{self.parameter_name}_{side}_1")
            if day in EMPTY_VALUES or time in EMPTY_VALUES:
                continue
            value = parse_datetime_str(f"{day} {time}")
            if value is not None:
                filters[f"{self.parameter_name}__{lookup}"] = timezone.make_aware(value)
        try:
            return queryset.filter(**filters)
        except (ValueError, ValidationError):
            return None
