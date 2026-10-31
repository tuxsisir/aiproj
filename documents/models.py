import uuid

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

from core.models import BaseModel
from stratas.models import StrataPlan


def document_upload_path(instance, filename):
    # Random name: files are only served through the permission-checked document_file view.
    return f"documents/{instance.strata_id}/{uuid.uuid4().hex}.pdf"


class Document(BaseModel):
    """A building document (bylaws, rules, minutes...) with an AI-generated summary."""

    class Category(models.TextChoices):
        BYLAWS = 'BYLAWS', 'Bylaws'
        RULES = 'RULES', 'Rules'
        MINUTES = 'MINUTES', 'Minutes'
        INSURANCE = 'INSURANCE', 'Insurance'
        FINANCIAL = 'FINANCIAL', 'Financial'
        OTHER = 'OTHER', 'Other'

    class SummaryStatus(models.TextChoices):
        PENDING = 'PENDING', 'Waiting'
        PROCESSING = 'PROCESSING', 'Summarizing'
        READY = 'READY', 'Ready'
        FAILED = 'FAILED', 'Failed'

    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.BYLAWS)
    file = models.FileField(upload_to=document_upload_path, validators=[FileExtensionValidator(['pdf'])])
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploaded_documents"
    )

    # Claude Files API id, so the PDF is uploaded to Claude once and referenced afterwards.
    claude_file_id = models.CharField(max_length=100, blank=True)

    # Structured summary: {"overview": str, "topics": [{"name", "points": [{"text", "pages"}]}], "key_numbers": [...]}
    summary = models.JSONField(default=dict, blank=True)
    summary_status = models.CharField(max_length=12, choices=SummaryStatus.choices, default=SummaryStatus.PENDING)
    summary_error = models.CharField(max_length=255, blank=True)
    summarized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['category', 'title']
        indexes = [models.Index(fields=['strata', 'category'])]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class DocumentQuestion(BaseModel):
    """A question asked across a building's documents, kept so answers stay findable."""
    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="document_questions")
    asked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="document_questions"
    )
    question = models.TextField()
    # Answer as segments so citations stay attached to the sentence they support:
    # [{"text": str, "citations": [{"document_id", "title", "page", "quote"}]}]
    answer = models.JSONField(default=list, blank=True)
    usage = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.question[:80]

    @property
    def sources(self):
        """Unique (document, page) pairs cited in the answer, in first-seen order."""
        seen, result = set(), []
        for segment in self.answer:
            for c in segment.get("citations", []):
                key = (c["document_id"], c["page"])
                if key not in seen:
                    seen.add(key)
                    result.append(c)
        return result
