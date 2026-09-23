from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


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
            roles.append(f"{m.get_role_display()} ({m.strata.plan_number})")
        return ", ".join(roles) if roles else "-"

    get_roles.short_description = "Strata Roles"
