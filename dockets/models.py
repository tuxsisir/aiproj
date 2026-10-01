import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone
from core.models import BaseModel, FieldTrackerMixin
from stratas.models import StrataPlan, Membership
from django.conf import settings

class Bylaw(BaseModel):
    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="bylaws")
    code = models.CharField(max_length=20)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    standard_fine = models.DecimalField(max_digits=10, decimal_places=2, default=200.00)
    is_archived = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_bylaws")

    class Meta:
        unique_together = ('strata', 'code')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.title}"


class Incident(FieldTrackerMixin, BaseModel):
    TRACKED_FIELDS = ['unit_number', 'strata_lot', 'bylaw_id', 'status', 'recipient_email']

    class Type(models.TextChoices):
        BYLAW = 'BYLAW', 'Bylaw Infraction'
        DEFICIENCY = 'DEFICIENCY', 'Common Property Deficiency'

    class Status(models.TextChoices):
        IN_REVIEW = 'IN_REVIEW', 'Awaiting Manager Review'
        NOTICE_ISSUED = 'NOTICE_ISSUED', 'Statutory Notice Issued'
        RESPONSE_RECEIVED = 'RESPONSE_RECEIVED', 'Response Received'
        VOTING_OPEN = 'VOTING_OPEN', 'Council Ballot Open'
        RESOLVED_FINED = 'RESOLVED_FINED', 'Fine Authorized'
        RESOLVED_DISMISSED = 'RESOLVED_DISMISSED', 'Closed / Dismissed'

    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="incidents")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="logged_incidents")
    
    incident_type = models.CharField(max_length=20, choices=Type.choices, default=Type.BYLAW)
    title = models.CharField(max_length=255)
    unit_number = models.CharField(max_length=50, blank=True)
    strata_lot = models.CharField(max_length=20, blank=True)
    bylaw = models.ForeignKey(Bylaw, on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents")
    
    description = models.TextField()
    evidence_image = models.ImageField(upload_to="incidents/evidence/", blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.IN_REVIEW)
    
    notice_issued_at = models.DateTimeField(null=True, blank=True)
    statutory_deadline = models.DateTimeField(null=True, blank=True)
    recipient_email = models.EmailField(blank=True)
    
    manager_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    owner_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Incident: {self.title} ({self.get_status_display()})"

    def calculate_and_set_deadline(self):
        """
        Computes BC Section 61 deemed service plus Section 135 response window, 
        totaling 14 days from current timestamp.
        """
        now = timezone.now()
        self.notice_issued_at = now
        self.statutory_deadline = now + timedelta(days=14)
        self.status = self.Status.NOTICE_ISSUED

    @property
    def days_remaining(self):
        if self.statutory_deadline:
            delta = self.statutory_deadline - timezone.now()
            return max(0, delta.days)
        return 0


class IncidentEvent(BaseModel):
    class EventType(models.TextChoices):
        RECURRENCE = 'RECURRENCE', 'Subsequent Occurrence'
        EVIDENCE = 'EVIDENCE', 'Additional Evidence'
        NOTE = 'NOTE', 'Manager / Council Note'
        UNIT_CORRECTED = 'UNIT_CORRECTED', 'Unit Corrected'
        STATUTORY_NOTICE = 'STATUTORY_NOTICE', 'S.135 Notice Dispatched'
        OWNER_STATEMENT = 'OWNER_STATEMENT', 'Owner Written Response'
        HEARING_REQUESTED = 'HEARING_REQUESTED', 'Council Hearing Requested'
        FINE_DISPATCHED = 'FINE_DISPATCHED', 'Official Fine Dispatched'

    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="events")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    description = models.TextField()
    evidence_file = models.FileField(upload_to="incidents/evidence_events/", null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['occurred_at']

    def __str__(self):
        return f"{self.get_event_type_display()} on {self.incident.title}"







class CouncilVote(models.Model):
    incident = models.ForeignKey(Incident, on_delete=models.CASCADE, related_name="votes")
    member = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name="incident_votes")
    approve_fine = models.BooleanField(help_text="True = levy fine, False = dismiss/warn")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('incident', 'member')

    def __str__(self):
        return f"Vote by {self.member.user.get_full_name()} on {self.incident.title}"
