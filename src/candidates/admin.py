from django.contrib import admin

from .models import Candidate, JobAlert, JobSearch, SavedPosting


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ("__str__", "email", "city", "experience_years", "is_open_to_work")
    list_filter = ("is_open_to_work", "education_level", "language")
    search_fields = ("first_name", "last_name", "email", "user__username")
    filter_horizontal = ("skills",)


@admin.register(SavedPosting)
class SavedPostingAdmin(admin.ModelAdmin):
    list_select_related = ("candidate", "posting")


@admin.register(JobAlert)
class JobAlertAdmin(admin.ModelAdmin):
    list_display = ("name", "candidate", "frequency", "is_active", "last_sent_at")
    list_filter = ("frequency", "is_active")
    filter_horizontal = ("skills",)


@admin.register(JobSearch)
class JobSearchAdmin(admin.ModelAdmin):
    """Read-only: rows are written by the job list (see candidates/search_log.py)."""

    list_display = (
        "query",
        "location",
        "work_mode",
        "results",
        "language",
        "created_at",
    )
    list_filter = (
        "work_mode",
        "employment_type",
        "seniority",
        "language",
        "created_at",
    )
    search_fields = ("query", "location")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
