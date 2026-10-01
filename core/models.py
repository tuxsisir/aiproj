import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey

class BaseModel(models.Model):
    """
    Abstract base model providing UUID primary key, 
    creation, and update timestamps.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class User(AbstractUser):
    """Custom User Model for the base project."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    brokerage_name = models.CharField(max_length=150, blank=True)
    
    def __str__(self):
        return self.username


class FieldTrackerMixin:
    """
    Snapshots field values on model initialization to detect dirty fields upon save.
    """
    TRACKED_FIELDS = []  # Specify fields to track in the child model

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initial_state = {
            field: getattr(self, field, None)
            for field in self.TRACKED_FIELDS
        }

    def get_dirty_fields(self):
        dirty = {}
        for field in self.TRACKED_FIELDS:
            current_value = getattr(self, field, None)
            initial_value = self._initial_state.get(field)
            if current_value != initial_value:
                dirty[field] = {
                    "from": str(initial_value) if initial_value is not None else None,
                    "to": str(current_value) if current_value is not None else None,
                }
        return dirty

    def reset_initial_state(self):
        self._initial_state = {
            field: getattr(self, field, None)
            for field in self.TRACKED_FIELDS
        }


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "CREATE", "Created"
        UPDATE = "UPDATE", "Updated"
        DELETE = "DELETE", "Deleted"
        STATUS_CHANGE = "STATUS_CHANGE", "Status Transitioned"
        NOTICE_DISPATCHED = "NOTICE_DISPATCHED", "Statutory Notice Dispatched"
        VOTE_CAST = "VOTE_CAST", "Council Ballot Submitted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Generic target object (e.g., Incident #42, Bylaw #12)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=255)
    content_object = GenericForeignKey('content_type', 'object_id')

    # Actor information
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs"
    )
    actor_email = models.EmailField(blank=True, help_text="Preserved snapshot in case user is deleted")
    actor_ip = models.GenericIPAddressField(null=True, blank=True)

    action = models.CharField(max_length=30, choices=Action.choices)
    
    # Human-readable summary for quick UI rendering
    summary = models.CharField(max_length=255, help_text="e.g. Changed Unit Number from 'Common Property' to '304'")

    # Detailed field-level diff: {"unit_number": {"from": "", "to": "304"}}
    changes = models.JSONField(default=dict, blank=True)

    # Immutable timestamp
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['actor', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.actor_email or 'System'} {self.action} on {self.content_type.model} #{self.object_id}"

    def save(self, *args, **kwargs):
        # Guarantee immutable audit record: prevent updates to existing rows
        if not self._state.adding:
            raise RuntimeError("AuditLog records are immutable and cannot be updated.")
        if self.actor and not self.actor_email:
            self.actor_email = self.actor.email
        super().save(*args, **kwargs)
