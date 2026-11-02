"""
The building calendar: every pillar contributes dated events here.

A source is a function (strata, start, end) -> iterable of Event for dates within [start, end].
New pillars (projects, maintenance) add a source to SOURCES; the calendar page needs no change.
"""
import datetime
from dataclasses import dataclass

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from dockets.models import Incident
from issues.models import Issue
from meetings.models import Meeting
from .models import KeyDate

SOON_DAYS = 3


@dataclass(frozen=True)
class Event:
    date: datetime.date
    title: str
    pillar: str  # "Key date", "Enforcement", ...
    url: str
    status: str = ""  # "", "soon", "overdue", "done" or "past"
    detail: str = ""


def events_between(strata, start, end):
    events = [event for source in SOURCES for event in source(strata, start, end)]
    return sorted(events, key=lambda e: (e.date, e.title))


def still_overdue(strata, before):
    """Missed deadlines dated before `before` (no lookback limit), so a month view never hides them."""
    today = timezone.localdate()
    waiting = strata.incidents.filter(
        status=Incident.Status.NOTICE_ISSUED, statutory_deadline__date__lt=min(before, today)
    ).order_by("statutory_deadline")
    return [_response_due(incident, today) for incident in waiting]


def key_date_events(strata, start, end):
    today = timezone.localdate()
    candidates = strata.key_dates.filter(Q(date__range=(start, end)) | Q(repeats_yearly=True, date__lte=end))
    for key_date in candidates:
        for day in key_date.occurrences(start, end):
            yield Event(
                date=day,
                title=key_date.title,
                pillar="Key date",
                url=reverse("schedule:key_date_update", args=[key_date.pk]),
                status="past" if day < today else deadline_status(day, today),
                detail=key_date.get_category_display(),
            )


def enforcement_events(strata, start, end):
    today = timezone.localdate()
    incidents = strata.incidents.filter(
        Q(statutory_deadline__date__range=(start, end)) | Q(notice_issued_at__date__range=(start, end))
    )
    for incident in incidents:
        if incident.notice_issued_at:
            issued = timezone.localtime(incident.notice_issued_at).date()
            if start <= issued <= end:
                yield Event(issued, f"Notice issued · {_label(incident)}", "Enforcement", _url(incident), "done", incident.title)
        if incident.statutory_deadline:
            event = _response_due(incident, today)
            if start <= event.date <= end:
                yield event


def issue_events(strata, start, end):
    """Fix-by dates of building issues; overdue only while the issue is still open."""
    today = timezone.localdate()
    for issue in strata.issues.filter(due_date__range=(start, end)):
        status = deadline_status(issue.due_date, today) if issue.is_open else "done"
        yield Event(issue.due_date, f"Fix by · {issue.title}", "Issue",
                    reverse("issues:detail", args=[issue.pk]), status, issue.location or issue.get_category_display())


def meeting_events(strata, start, end):
    """Meetings by their local date. A planned meeting whose day has passed shows overdue until it's recorded."""
    today = timezone.localdate()
    window = (_day_start(start), _day_start(end + datetime.timedelta(days=1)))
    meetings = strata.meetings.exclude(status=Meeting.Status.CANCELLED).filter(starts_at__gte=window[0],
                                                                              starts_at__lt=window[1])
    for meeting in meetings:
        when = timezone.localtime(meeting.starts_at)
        if meeting.status == Meeting.Status.PLANNED:
            status = deadline_status(when.date(), today) if when.date() >= today else "overdue"
        else:
            status = "done"
        detail = f"{when.hour % 12 or 12}:{when:%M} {'am' if when.hour < 12 else 'pm'}"  # "7:00 pm", portable
        if meeting.location:
            detail += f" · {meeting.location}"
        yield Event(when.date(), meeting.get_kind_display(), "Meeting", reverse("meetings:detail", args=[meeting.pk]),
                    status, detail)


def _day_start(day):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time.min))


def _response_due(incident, today):
    """The owner's response deadline; only overdue while the case still waits on the owner."""
    deadline = timezone.localtime(incident.statutory_deadline).date()
    waiting = incident.status == Incident.Status.NOTICE_ISSUED
    status = deadline_status(deadline, today) if waiting else "done"
    return Event(deadline, f"Response due · {_label(incident)}", "Enforcement", _url(incident), status, incident.title)


def _label(incident):
    return f"Unit {incident.unit_number}" if incident.unit_number else incident.title


def _url(incident):
    return reverse("dockets:incident_detail", args=[incident.pk])


def deadline_status(day, today):
    if day < today:
        return "overdue"
    if (day - today).days <= SOON_DAYS:
        return "soon"
    return ""


SOURCES = [key_date_events, enforcement_events, issue_events, meeting_events]
