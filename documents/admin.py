from django.contrib import admin

from .models import Document, DocumentQuestion


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "strata", "category", "summary_status", "uploaded_by", "created_at")
    list_filter = ("summary_status", "category", "strata")
    search_fields = ("title",)
    readonly_fields = ("claude_file_id", "summarized_at")


@admin.register(DocumentQuestion)
class DocumentQuestionAdmin(admin.ModelAdmin):
    list_display = ("question", "strata", "asked_by", "created_at")
    list_filter = ("strata",)
    search_fields = ("question",)
    readonly_fields = ("answer", "usage")
