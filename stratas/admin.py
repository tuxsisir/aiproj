from django.contrib import admin
from .models import StrataPlan, Membership, StrataInvitation

class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    fields = ('user', 'role', 'unit_number', 'is_active', 'joined_at')
    readonly_fields = ('joined_at',)

@admin.register(StrataPlan)
class StrataPlanAdmin(admin.ModelAdmin):
    list_display = ('plan_number', 'name', 'city', 'state_province', 'country', 'total_units', 'created_at')
    search_fields = ('plan_number', 'name', 'street_address', 'city')
    list_filter = ('state_province', 'country')
    inlines = [MembershipInline]

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'strata', 'role', 'unit_number', 'is_active', 'joined_at')
    list_filter = ('role', 'is_active', 'strata')
    search_fields = ('user__email', 'strata__plan_number', 'strata__name', 'unit_number')

@admin.register(StrataInvitation)
class StrataInvitationAdmin(admin.ModelAdmin):
    list_display = ('email', 'strata', 'role', 'invited_by', 'is_accepted', 'created_at')
    list_filter = ('role', 'is_accepted')
    search_fields = ('email', 'strata__plan_number')
    readonly_fields = ('token', 'created_at')
