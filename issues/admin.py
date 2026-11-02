from django.contrib import admin

from .models import Issue, IssueUpdate


class IssueUpdateInline(admin.TabularInline):
    model = IssueUpdate
    extra = 0
    readonly_fields = ("kind", "author", "body", "created_at")
    can_delete = False


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ("title", "strata", "status", "priority", "category", "assigned_to", "created_at")
    list_filter = ("status", "priority", "category")
    search_fields = ("title", "location", "strata__name", "strata__plan_number")
    inlines = [IssueUpdateInline]
