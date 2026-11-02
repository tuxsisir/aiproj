from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import BaseModel, FieldTrackerMixin
from stratas.models import StrataPlan


class MeetingQuerySet(models.QuerySet):
    def upcoming(self):
        return self.filter(status=Meeting.Status.PLANNED, starts_at__gte=timezone.now())

    def not_recorded(self):
        """Planned meetings whose time has passed but nobody recorded them as held."""
        return self.filter(status=Meeting.Status.PLANNED, starts_at__lt=timezone.now())

    def awaiting_approval(self):
        return self.filter(status=Meeting.Status.HELD)


class Meeting(FieldTrackerMixin, BaseModel):
    """
    A council or general meeting: an agenda before, minutes after, approved by council.
    Lifecycle: PLANNED (agenda editable) → HELD (minutes in draft) → APPROVED (locked). PLANNED → CANCELLED.
    """

    TRACKED_FIELDS = ["kind", "starts_at", "location", "status"]

    class Kind(models.TextChoices):
        COUNCIL = "COUNCIL", "Council meeting"
        AGM = "AGM", "Annual general meeting"
        SGM = "SGM", "Special general meeting"

    class Status(models.TextChoices):
        PLANNED = "PLANNED", "Planned"
        HELD = "HELD", "Minutes in draft"
        APPROVED = "APPROVED", "Minutes approved"
        CANCELLED = "CANCELLED", "Cancelled"

    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="meetings")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.COUNCIL)
    starts_at = models.DateTimeField()
    location = models.CharField(max_length=160, blank=True, help_text="e.g. Amenity room, or a video call link")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="meetings_planned"
    )

    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="meetings_attended")
    guests = models.CharField(max_length=255, blank=True, help_text="Others present, e.g. an owner for a hearing")
    held_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="minutes_approved"
    )

    objects = MeetingQuerySet.as_manager()

    class Meta:
        ordering = ["-starts_at"]
        indexes = [models.Index(fields=["strata", "status"])]

    def __str__(self):
        when = timezone.localtime(self.starts_at)
        return f"{self.get_kind_display()}, {when:%b} {when.day}, {when.year}"

    @property
    def agenda_editable(self):
        return self.status == self.Status.PLANNED

    @property
    def minutes_editable(self):
        return self.status in (self.Status.PLANNED, self.Status.HELD)


class AgendaItem(BaseModel):
    """
    One item on a meeting's agenda, and what was minuted and decided about it.
    Linked to the issue or enforcement case it came from, so the decision lands on that item's timeline.
    In-camera items (hearings, anything about a specific owner) are left out of the owners' copy of the minutes.
    """

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveSmallIntegerField(default=0)
    title = models.CharField(max_length=200)
    details = models.TextField(blank=True, help_text="Background for the council before the meeting")
    in_camera = models.BooleanField(default=False)
    issue = models.ForeignKey(
        "issues.Issue", on_delete=models.SET_NULL, null=True, blank=True, related_name="agenda_items"
    )
    incident = models.ForeignKey(
        "dockets.Incident", on_delete=models.SET_NULL, null=True, blank=True, related_name="agenda_items"
    )
    minutes = models.TextField(blank=True)
    decision = models.TextField(blank=True)

    class Meta:
        ordering = ["position", "created_at"]

    def __str__(self):
        return self.title
