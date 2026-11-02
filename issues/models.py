from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel, FieldTrackerMixin
from stratas.models import StrataPlan


class IssueQuerySet(models.QuerySet):
    def open(self):
        return self.exclude(status__in=Issue.CLOSED)

    def closed(self):
        return self.filter(status__in=Issue.CLOSED)


class Issue(FieldTrackerMixin, BaseModel):
    """
    Something wrong with the building that should get fixed (a broken door, out-of-sync cameras, a leak).
    Owned, tracked and closed with an outcome. Unlike an enforcement case, there is no procedure or CRT path.
    """

    TRACKED_FIELDS = ["title", "category", "location", "priority", "status", "assigned_to_id", "vendor", "due_date"]

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"  # raised, nobody has responded yet
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed, no action"

    class Category(models.TextChoices):
        MAINTENANCE = "MAINTENANCE", "Maintenance & repairs"
        SECURITY = "SECURITY", "Security"
        CLEANLINESS = "CLEANLINESS", "Cleanliness & garbage"
        SAFETY = "SAFETY", "Safety"
        PARKING = "PARKING", "Parkade & parking"
        AMENITIES = "AMENITIES", "Amenities & common areas"
        OTHER = "OTHER", "Other"

    class Priority(models.TextChoices):
        LOW = "LOW", "Low"
        NORMAL = "NORMAL", "Normal"
        HIGH = "HIGH", "High"
        URGENT = "URGENT", "Urgent"

    CLOSED = [Status.RESOLVED, Status.CLOSED]

    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="issues")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.MAINTENANCE)
    location = models.CharField(max_length=120, blank=True, help_text="e.g. Storage room 5, parkade level P2")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)

    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="issues_raised"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="issues_assigned"
    )
    vendor = models.CharField(max_length=120, blank=True)
    due_date = models.DateField(null=True, blank=True, help_text="Target date to have it fixed")
    source_email = models.ForeignKey(
        "inbox.InboundEmail", on_delete=models.SET_NULL, null=True, blank=True, related_name="issues"
    )

    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    outcome = models.TextField(blank=True)
    last_activity_at = models.DateTimeField(default=timezone.now)

    objects = IssueQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["strata", "status"])]

    def __str__(self):
        return self.title

    @property
    def is_open(self):
        return self.status not in self.CLOSED


class IssueUpdate(BaseModel):
    """One entry on an issue's timeline. Entries are never edited; a correction is a new entry."""

    class Kind(models.TextChoices):
        CREATED = "CREATED", "Raised"
        STATUS = "STATUS", "Status changed"
        ASSIGNED = "ASSIGNED", "Assigned"
        DETAILS = "DETAILS", "Details changed"
        COMMENT = "COMMENT", "Comment"

    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    body = models.TextField()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} on {self.issue}"
