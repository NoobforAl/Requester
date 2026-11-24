from django.contrib import admin
from unfold.admin import TabularInline
from unfold.contrib.filters.admin import (
    ChoicesDropdownFilter,
    RelatedDropdownFilter,
)
from unfold.decorators import display

from requester.unfold_admin import ModelAdmin, RangeDateTimeFilter

from .models import Application, ApplicationEvent

#: Status -> label color in the list.
STATUS_COLORS = {
    "pending": "info",
    "in_review": "info",
    "shortlisted": "warning",
    "accepted": "success",
    "rejected": "danger",
    "withdrawn": "danger",
}


class ApplicationEventInline(TabularInline):
    model = ApplicationEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "actor", "note", "created_at")
    can_delete = False
    tab = True  # its own tab on the application page

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Application)
class ApplicationAdmin(ModelAdmin):
    list_display = ("candidate", "posting", "employer", "state", "applied_at")
    list_filter = (
        ("status", ChoicesDropdownFilter),
        ("posting__employer", RelatedDropdownFilter),
        ("applied_at", RangeDateTimeFilter),
    )
    list_filter_submit = True
    list_select_related = ("candidate", "posting__employer")
    search_fields = (
        "candidate__first_name",
        "candidate__last_name",
        "candidate__email",
        "posting__title",
        "posting__employer__name",
    )
    autocomplete_fields = ("candidate", "posting")
    readonly_fields = ("ai_summary", "ai_provider", "applied_at", "updated_at")
    date_hierarchy = "applied_at"
    inlines = (ApplicationEventInline,)
    warn_unsaved_form = True

    @display(description="Status", ordering="status", label=STATUS_COLORS)
    def state(self, obj):
        return obj.status, obj.get_status_display()

    @display(description="Employer", ordering="posting__employer__name")
    def employer(self, obj):
        return obj.posting.employer.name
