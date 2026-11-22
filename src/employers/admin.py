from django.contrib import admin

from .models import Employer, JobPosting, Skill


@admin.register(Employer)
class EmployerAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_email", "city", "industry", "language")
    list_filter = ("size", "language")
    search_fields = ("name", "contact_email", "user__username")


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "employer",
        "location",
        "work_mode",
        "employment_type",
        "is_active",
        "deadline",
    )
    list_filter = ("is_active", "work_mode", "employment_type", "seniority")
    search_fields = ("title", "description", "employer__name", "location")
    list_select_related = ("employer",)
    filter_horizontal = ("skills",)
