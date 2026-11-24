from django.contrib import admin
from unfold.contrib.filters.admin import (
    ChoicesDropdownFilter,
    RangeNumericFilter,
)
from unfold.decorators import display

from requester.unfold_admin import ModelAdmin, RangeDateTimeFilter

from .models import Candidate, JobAlert, JobSearch, SavedPosting

#: Yes/no columns as colored labels.
YES_NO = {"yes": "success", "no": "danger"}


@admin.register(Candidate)
class CandidateAdmin(ModelAdmin):
    list_display = ("person", "city", "experience_years", "open_to_work", "created_at")
    list_filter = (
        "is_open_to_work",
        ("education_level", ChoicesDropdownFilter),
        ("preferred_work_mode", ChoicesDropdownFilter),
        ("language", ChoicesDropdownFilter),
        ("experience_years", RangeNumericFilter),
        ("created_at", RangeDateTimeFilter),
    )
    list_filter_submit = True
    search_fields = ("first_name", "last_name", "email", "user__username", "city")
    filter_horizontal = ("skills",)
    warn_unsaved_form = True

    @display(description="Candidate", header=True, ordering="last_name")
    def person(self, obj):
        # Two lines (name, e-mail) and the initials as the avatar.
        initials = f"{obj.first_name[:1]}{obj.last_name[:1]}".upper()
        return f"{obj.first_name} {obj.last_name}", obj.email, initials

    @display(description="Open to work", ordering="is_open_to_work", label=YES_NO)
    def open_to_work(self, obj):
        return ("yes", "Yes") if obj.is_open_to_work else ("no", "No")


@admin.register(SavedPosting)
class SavedPostingAdmin(ModelAdmin):
    list_display = ("candidate", "posting", "created_at")
    list_select_related = ("candidate", "posting")
    list_filter = (("created_at", RangeDateTimeFilter),)
    list_filter_submit = True
    autocomplete_fields = ("candidate", "posting")


@admin.register(JobAlert)
class JobAlertAdmin(ModelAdmin):
    list_display = ("name", "candidate", "frequency", "active", "last_sent_at")
    list_filter = ("is_active", ("frequency", ChoicesDropdownFilter))
    list_filter_submit = True
    list_select_related = ("candidate",)
    search_fields = ("name", "keywords", "candidate__email")
    autocomplete_fields = ("candidate",)
    filter_horizontal = ("skills",)

    @display(description="Active", ordering="is_active", label=YES_NO)
    def active(self, obj):
        return ("yes", "On") if obj.is_active else ("no", "Off")


@admin.register(JobSearch)
class JobSearchAdmin(ModelAdmin):
    """Read-only: rows are written by the job list (see candidates/search_log.py)."""

    list_display = ("query", "location", "work_mode", "found", "language", "created_at")
    list_filter = (
        ("work_mode", ChoicesDropdownFilter),
        ("employment_type", ChoicesDropdownFilter),
        ("seniority", ChoicesDropdownFilter),
        ("results", RangeNumericFilter),
        ("created_at", RangeDateTimeFilter),
    )
    list_filter_submit = True
    search_fields = ("query", "location")
    date_hierarchy = "created_at"

    @display(
        description="Jobs found",
        ordering="results",
        label={"none": "danger", "some": "success"},
    )
    def found(self, obj):
        return ("none" if obj.results == 0 else "some"), str(obj.results)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
