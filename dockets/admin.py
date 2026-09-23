from django.contrib import admin
from .models import Bylaw, Incident, IncidentResponse, CouncilVote

class IncidentResponseInline(admin.StackedInline):
    model = IncidentResponse
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
    inlines = [IncidentResponseInline, CouncilVoteInline]

@admin.register(IncidentResponse)
class IncidentResponseAdmin(admin.ModelAdmin):
    list_display = ('incident', 'response_type', 'submitted_at')
    list_filter = ('response_type',)

@admin.register(CouncilVote)
class CouncilVoteAdmin(admin.ModelAdmin):
    list_display = ('incident', 'member', 'approve_fine', 'created_at')
    list_filter = ('approve_fine',)
