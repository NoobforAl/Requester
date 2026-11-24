from django.contrib import admin
from django.db.models import Count, Q
from django.utils import timezone
from unfold.contrib.filters.admin import (
    ChoicesDropdownFilter,
    RangeDateFilter,
    RangeNumericFilter,
)
from unfold.decorators import display

from requester.unfold_admin import ModelAdmin, RangeDateTimeFilter

from .models import Employer, JobPosting, Skill, WorkMode


def open_q(prefix: str = "") -> Q:
    """``JobPosting.objects.open()`` as a Q, for counting through a relation."""
    return Q(**{f"{prefix}is_active": True}) & (
        Q(**{f"{prefix}deadline__isnull": True})
        | Q(**{f"{prefix}deadline__gte": timezone.localdate()})
    )


@admin.register(Employer)
class EmployerAdmin(ModelAdmin):
    list_display = (
        "name",
        "contact_email",
        "city",
        "industry",
        "open_jobs",
        "language",
    )
    list_filter = (("size", ChoicesDropdownFilter), ("language", ChoicesDropdownFilter))
    list_filter_submit = True
    search_fields = ("name", "contact_email", "user__username")
    warn_unsaved_form = True

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(n_open=Count("postings", filter=open_q("postings__")))
        )

    @display(description="Open jobs", ordering="n_open")
    def open_jobs(self, obj) -> int:
        return obj.n_open


@admin.register(Skill)
class SkillAdmin(ModelAdmin):
    list_display = ("name", "jobs", "candidates")
    search_fields = ("name",)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(
                n_jobs=Count("postings", distinct=True),
                n_candidates=Count("candidates", distinct=True),
            )
        )

    @display(description="Job postings", ordering="n_jobs")
    def jobs(self, obj) -> int:
        return obj.n_jobs

    @display(description="Candidates", ordering="n_candidates")
    def candidates(self, obj) -> int:
        return obj.n_candidates


@admin.register(JobPosting)
class JobPostingAdmin(ModelAdmin):
    list_display = (
        "title",
        "employer",
        "location",
        "mode",
        "employment_type",
        "state",
        "applicants",
        "deadline",
        "created_at",
    )
    list_filter = (
        "is_active",
        ("work_mode", ChoicesDropdownFilter),
        ("employment_type", ChoicesDropdownFilter),
        ("seniority", ChoicesDropdownFilter),
        ("salary_max", RangeNumericFilter),
        ("deadline", RangeDateFilter),
        ("created_at", RangeDateTimeFilter),
    )
    list_filter_submit = True
    search_fields = ("title", "description", "employer__name", "location")
    list_select_related = ("employer",)
    autocomplete_fields = ("employer",)
    filter_horizontal = ("skills",)
    date_hierarchy = "created_at"
    warn_unsaved_form = True

    def get_queryset(self, request):
        return (
            super().get_queryset(request).annotate(n_applications=Count("applications"))
        )

    @display(
        description="Work mode",
        ordering="work_mode",
        label={
            WorkMode.REMOTE: "success",
            WorkMode.HYBRID: "info",
            WorkMode.ONSITE: "warning",
        },
    )
    def mode(self, obj):
        return obj.work_mode, obj.get_work_mode_display()

    @display(
        description="Status",
        label={"open": "success", "closed": "danger", "expired": "warning"},
    )
    def state(self, obj):
        if not obj.is_active:
            return "closed", "Closed"
        if not obj.is_open:
            return "expired", "Past deadline"
        return "open", "Open"

    @display(description="Applications", ordering="n_applications")
    def applicants(self, obj) -> int:
        return obj.n_applications
