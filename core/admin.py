from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AuditLog, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "get_roles",
        "is_active",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups")
    search_fields = ("username", "first_name", "last_name", "email")

    # Add our custom 'avatar' field to the detail view
    fieldsets = UserAdmin.fieldsets + (
        (
            "Custom Profile Info",
            {
                "fields": ("avatar",),
            },
        ),
    )

    def get_queryset(self, request):
        # Prevent N+1 queries by prefetching memberships and their associated strata plans
        qs = super().get_queryset(request)
        return qs.prefetch_related("memberships__strata")

    def get_roles(self, obj):
        roles = []
        for m in obj.memberships.all():
            roles.append(f"{m.title} · {m.get_status_display()} ({m.strata.plan_number})")
        return ", ".join(roles) if roles else "-"

    get_roles.short_description = "Strata Roles"


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only: audit records are immutable."""
    list_display = ("created_at", "action", "summary", "actor_email", "content_type", "object_id")
    list_filter = ("action", "content_type")
    search_fields = ("summary", "actor_email", "object_id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
