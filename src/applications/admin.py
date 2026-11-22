from django.contrib import admin

from .models import Application, ApplicationEvent


class ApplicationEventInline(admin.TabularInline):
    model = ApplicationEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "actor", "note", "created_at")
    can_delete = False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("candidate", "posting", "status", "applied_at")
    list_filter = ("status",)
    list_select_related = ("candidate", "posting")
    inlines = (ApplicationEventInline,)
