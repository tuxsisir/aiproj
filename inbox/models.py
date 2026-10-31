import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from core.models import BaseModel
from stratas.models import StrataPlan


class Inbox(BaseModel):
    """A building's forwarding address: <local_part>@INBOUND_EMAIL_DOMAIN."""
    strata = models.OneToOneField(StrataPlan, on_delete=models.CASCADE, related_name="inbox")
    local_part = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.address

    @property
    def address(self):
        return f"{self.local_part}@{settings.INBOUND_EMAIL_DOMAIN}"

    @staticmethod
    def new_local_part(strata):
        # Random suffix so the address can't be guessed from the plan number.
        return f"{slugify(strata.plan_number)}-{secrets.token_hex(3)}"


class InboundEmail(BaseModel):
    """An email a member forwarded to their building's inbox, with an AI summary of the issue."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Waiting'
        PROCESSING = 'PROCESSING', 'Summarizing'
        READY = 'READY', 'Ready'
        FAILED = 'FAILED', 'Failed'

    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="inbound_emails")
    forwarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="forwarded_emails"
    )
    # Provider event id, so webhook retries don't create duplicates.
    provider_event_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    from_email = models.EmailField()
    from_name = models.CharField(max_length=200, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body_text = models.TextField(blank=True)
    received_at = models.DateTimeField(default=timezone.now)
    # [{"filename", "content_type", "size"}] (contents are not stored yet)
    attachments = models.JSONField(default=list, blank=True)

    # {"title", "summary", "category", "urgency", "people", "action_items", "open_questions", "suggested_next_step"}
    summary = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['-received_at']
        indexes = [models.Index(fields=['strata', '-received_at'])]

    def __str__(self):
        return self.subject or f"Email from {self.from_email}"

    @property
    def title(self):
        return self.summary.get("title") or self.subject or "(no subject)"
