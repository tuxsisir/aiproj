from django.contrib import admin
from .models import StrataPlan, Membership, StrataInvitation
from . import services

class MembershipInline(admin.TabularInline):
    model = Membership
    fk_name = 'strata'
    extra = 0
    fields = ('user', 'role', 'position', 'unit_number', 'status', 'joined_at')
    readonly_fields = ('joined_at',)

@admin.register(StrataPlan)
class StrataPlanAdmin(admin.ModelAdmin):
    list_display = ('plan_number', 'name', 'city', 'state_province', 'country', 'total_units', 'created_at')
    search_fields = ('plan_number', 'name', 'street_address', 'city')
    list_filter = ('state_province', 'country')
    inlines = [MembershipInline]

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'strata', 'role', 'position', 'unit_number', 'status', 'joined_at', 'reviewed_by')
    list_filter = ('status', 'role', 'strata')
    search_fields = ('user__email', 'strata__plan_number', 'strata__name', 'unit_number')
    readonly_fields = ('reviewed_by', 'reviewed_at')
    list_select_related = ('user', 'strata', 'reviewed_by')
    actions = ['approve_selected', 'reject_selected']

    @admin.action(description="Approve selected memberships")
    def approve_selected(self, request, queryset):
        for membership in queryset.pending().select_related('user', 'strata'):
            services.approve_membership(membership, request.user)
        self.message_user(request, "Selected pending memberships approved.")

    @admin.action(description="Reject selected memberships")
    def reject_selected(self, request, queryset):
        for membership in queryset.pending().select_related('user', 'strata'):
            services.reject_membership(membership, request.user)
        self.message_user(request, "Selected pending memberships rejected.")

@admin.register(StrataInvitation)
class StrataInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'strata', 'role', 'invited_by', 'is_accepted', 'created_at')
    list_filter = ('role', 'is_accepted')
    search_fields = ('email', 'strata__plan_number')
    readonly_fields = ('token', 'created_at')
