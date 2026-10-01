from django.contrib import admin
from .models import Bylaw, Incident, CouncilVote, IncidentEvent

class IncidentEventInline(admin.StackedInline):
    model = IncidentEvent
    extra = 0

class CouncilVoteInline(admin.TabularInline):
    model = CouncilVote
    extra = 0

@admin.register(Bylaw)
class BylawAdmin(admin.ModelAdmin):
    list_display = ('code', 'title', 'strata', 'standard_fine')
    list_filter = ('strata',)
    search_fields = ('code', 'title')

@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ('title', 'strata', 'incident_type', 'status', 'created_at')
    list_filter = ('status', 'incident_type', 'strata')
    search_fields = ('title', 'unit_number', 'description')
    inlines = [IncidentEventInline, CouncilVoteInline]

@admin.register(IncidentEvent)
class IncidentEventAdmin(admin.ModelAdmin):
    list_display = ('incident', 'event_type', 'created_at')
    list_filter = ('event_type',)

@admin.register(CouncilVote)
class CouncilVoteAdmin(admin.ModelAdmin):
    list_display = ('incident', 'member', 'approve_fine', 'created_at')
    list_filter = ('approve_fine',)
