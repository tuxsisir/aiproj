from django.contrib import admin

from .models import AgendaItem, Meeting


class AgendaItemInline(admin.TabularInline):
    model = AgendaItem
    extra = 0
    fields = ["position", "title", "in_camera", "issue", "incident", "decision"]
    raw_id_fields = ["issue", "incident"]


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ["__str__", "strata", "status", "starts_at"]
    list_filter = ["status", "kind", "strata"]
    inlines = [AgendaItemInline]
    raw_id_fields = ["created_by", "approved_by"]
    filter_horizontal = ["attendees"]
