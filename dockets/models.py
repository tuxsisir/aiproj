import uuid
from datetime import timedelta
from django.db import models
from django.utils import timezone
from core.models import BaseModel
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


class Incident(BaseModel):
    class Type(models.TextChoices):
        BYLAW = 'BYLAW', 'Bylaw Infraction'
        DEFICIENCY = 'DEFICIENCY', 'Common Property Deficiency'

    class Status(models.TextChoices):
        LOGGED = 'LOGGED', 'Draft/Newly submitted'
        PENDING_MANAGER = 'PENDING_MANAGER', 'Awaiting manager review'
        NOTICE_ISSUED = 'NOTICE_ISSUED', 'Formal notice sent, statutory clock running'
        RESPONSE_RECEIVED = 'RESPONSE_RECEIVED', 'Owner submitted written statement'
        HEARING_REQUESTED = 'HEARING_REQUESTED', 'Owner requested in-person council hearing'
        VOTING_OPEN = 'VOTING_OPEN', 'Ready for digital council ballot'
        RESOLVED_FINED = 'RESOLVED_FINED', 'Fine authorized and posted'
        RESOLVED_DISMISSED = 'RESOLVED_DISMISSED', 'Dismissed or warning issued'

    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="incidents")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="logged_incidents")
    
    incident_type = models.CharField(max_length=20, choices=Type.choices, default=Type.BYLAW)
    title = models.CharField(max_length=255)
    unit_number = models.CharField(max_length=50, blank=True)
    bylaw = models.ForeignKey(Bylaw, on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents")
    
    description = models.TextField()
    evidence_image = models.ImageField(upload_to="incidents/evidence/", blank=True, null=True)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.LOGGED)
    
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
        Computes BC Section 61 deemed service (4 days) plus Section 135 response window (14 days), 
        totaling 18 days from current timestamp.
        """
        now = timezone.now()
        self.notice_issued_at = now
        self.statutory_deadline = now + timedelta(days=18)
        self.status = self.Status.NOTICE_ISSUED

    @property
    def days_remaining(self):
        if self.statutory_deadline:
            delta = self.statutory_deadline - timezone.now()
            return max(0, delta.days)
        return 0


class IncidentResponse(models.Model):
    class ResponseType(models.TextChoices):
        WRITTEN = 'WRITTEN', 'Submit Written Explanation'
        HEARING = 'HEARING', 'Request In-Person Hearing'

    incident = models.OneToOneField(Incident, on_delete=models.CASCADE, related_name="response")
    response_type = models.CharField(max_length=20, choices=ResponseType.choices)
    statement = models.TextField(blank=True)
    counter_evidence = models.FileField(upload_to="incidents/responses/", blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Response for {self.incident.title}"


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
