from django.contrib import admin

from .models import InboundEmail, Inbox


@admin.register(Inbox)
class InboxAdmin(admin.ModelAdmin):
    list_display = ("local_part", "strata", "created_at")
    search_fields = ("local_part", "strata__plan_number")


@admin.register(InboundEmail)
class InboundEmailAdmin(admin.ModelAdmin):
    list_display = ("subject", "strata", "from_email", "status", "received_at")
    list_filter = ("status", "strata")
    search_fields = ("subject", "from_email")
    readonly_fields = ("provider_event_id", "summary", "attachments")
