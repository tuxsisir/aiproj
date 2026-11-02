import datetime

from django.conf import settings
from django.db import models

from core.models import BaseModel, FieldTrackerMixin
from stratas.models import StrataPlan


class KeyDate(FieldTrackerMixin, BaseModel):
    """A date the building must not miss (AGM, insurance renewal, an inspection), entered by hand."""

    TRACKED_FIELDS = ["title", "date", "category", "repeats_yearly", "note"]

    class Category(models.TextChoices):
        MEETING = "MEETING", "Meeting"
        INSURANCE = "INSURANCE", "Insurance"
        INSPECTION = "INSPECTION", "Inspection"
        FINANCE = "FINANCE", "Finance"
        CONTRACT = "CONTRACT", "Contract"
        OTHER = "OTHER", "Other"

    strata = models.ForeignKey(StrataPlan, on_delete=models.CASCADE, related_name="key_dates")
    title = models.CharField(max_length=120)
    date = models.DateField()
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    note = models.TextField(blank=True)
    repeats_yearly = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="key_dates_added"
    )

    class Meta:
        ordering = ["date", "title"]
        indexes = [models.Index(fields=["strata", "date"])]

    def __str__(self):
        return f"{self.title} ({self.date})"

    def occurrences(self, start, end):
        """Dates of this key date within [start, end]; yearly ones repeat from their first date on."""
        if not self.repeats_yearly:
            return [self.date] if start <= self.date <= end else []
        found = []
        for year in range(max(start.year, self.date.year), end.year + 1):
            day = _same_day_in(year, self.date)
            if start <= day <= end:
                found.append(day)
        return found


def _same_day_in(year, date):
    try:
        return date.replace(year=year)
    except ValueError:  # 29 Feb in a non-leap year
        return datetime.date(year, 2, 28)
