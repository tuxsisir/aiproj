"""
Meeting lifecycle: plan (agenda from open items) → record minutes → mark held → council approves.
Once council approves the minutes, each decision lands on the timeline of the issue or enforcement case it was
about. Not before: draft minutes can still be corrected, and a case timeline is an append-only legal record.
"""
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from core import emails
from core.models import AuditLog
from core.services import record_audit_log
from dockets.models import Incident, IncidentEvent
from issues.models import Issue, IssueUpdate
from stratas.models import Membership
from stratas.services import member_emails
from .models import AgendaItem, Meeting

CLOSED_CASES = [Incident.Status.RESOLVED_FINED, Incident.Status.RESOLVED_DISMISSED]

# Standard items around the business of the day, by kind of meeting.
OPENING = {
    Meeting.Kind.COUNCIL: ["Call to order", "Approval of the agenda", "Approval of the previous minutes",
                           "Financial report", "Manager's report"],
    Meeting.Kind.AGM: ["Call to order and quorum", "Proof of notice", "Approval of the agenda",
                       "Approval of the previous general meeting minutes", "Approval of the budget",
                       "Election of council"],
    Meeting.Kind.SGM: ["Call to order and quorum", "Proof of notice", "Approval of the agenda"],
}
CLOSING = ["New business", "Adjournment"]
PREVIOUS_MINUTES = "Approval of the previous minutes"


def open_items(strata):
    """What could go on an agenda: open building issues and enforcement cases still in progress."""
    issues = strata.issues.open().select_related("assigned_to").order_by("created_at")
    cases = strata.incidents.exclude(status__in=CLOSED_CASES).select_related("bylaw").order_by("created_at")
    return issues, cases


@transaction.atomic
def plan_meeting(strata, user, *, kind, starts_at, location="", issues=(), cases=(), request=None):
    meeting = Meeting.objects.create(strata=strata, kind=kind, starts_at=starts_at, location=location,
                                     created_by=user)
    build_agenda(meeting, issues, cases)

    record_audit_log(meeting, user, action=AuditLog.Action.CREATE, request=request)
    others = [e for e in member_emails(strata) if e != user.email]
    transaction.on_commit(lambda: emails.send("meeting_scheduled", others,
                                              {"meeting": meeting, "items": list(meeting.items.all())}))
    return meeting


def build_agenda(meeting, issues=(), cases=()):
    """Standard items for this kind of meeting around one item per chosen issue and (in camera) case."""
    opening = list(OPENING[meeting.kind])
    if PREVIOUS_MINUTES in opening and not meeting.strata.meetings.exclude(pk=meeting.pk).filter(
            status__in=[Meeting.Status.HELD, Meeting.Status.APPROVED]).exists():
        opening.remove(PREVIOUS_MINUTES)  # the building's first meeting on CivicDesk

    items = [AgendaItem(title=title) for title in opening]
    items += [AgendaItem(title=f"Issue: {issue.title}", issue=issue, details=_issue_brief(issue))
              for issue in issues]
    items += [AgendaItem(title=f"Enforcement: {_case_label(case)}", incident=case, in_camera=True,
                         details=f"{case.get_status_display()}." + (f" Bylaw {case.bylaw.code}." if case.bylaw else ""))
              for case in cases]
    items += [AgendaItem(title=title) for title in CLOSING]
    for position, item in enumerate(items, start=1):
        item.meeting, item.position = meeting, position
    AgendaItem.objects.bulk_create(items)


def add_item(meeting, *, title, details="", in_camera=False, user=None, request=None):
    """New items go just before the closing items (New business, Adjournment)."""
    closing = meeting.items.filter(title__in=CLOSING, issue__isnull=True, incident__isnull=True)
    first_closing = closing.order_by("position").first()
    position = first_closing.position if first_closing else (meeting.items.aggregate(m=Max("position"))["m"] or 0) + 1
    meeting.items.filter(position__gte=position).update(position=F("position") + 1)
    item = AgendaItem.objects.create(meeting=meeting, position=position, title=title, details=details,
                                     in_camera=in_camera)
    record_audit_log(meeting, user, action=AuditLog.Action.UPDATE, request=request,
                     custom_summary=f"Agenda item added: {title}")
    return item


def move_item(item, up):
    items = list(item.meeting.items.all())
    i = items.index(item)
    j = i - 1 if up else i + 1
    if 0 <= j < len(items):
        items[i], items[j] = items[j], items[i]
        for position, each in enumerate(items, start=1):
            if each.position != position:
                each.position = position
                each.save(update_fields=["position"])


def remove_item(item, user=None, request=None):
    item.delete()
    record_audit_log(item.meeting, user, action=AuditLog.Action.UPDATE, request=request,
                     custom_summary=f"Agenda item removed: {item.title}")


def record_minutes(item, *, minutes, decision, user=None, request=None):
    """Save one item's minutes; changes are audited because draft minutes are a governance record."""
    minutes, decision = minutes.strip(), decision.strip()
    # Compare with the stored row: a bound ModelForm has already copied the new text onto `item`.
    stored = AgendaItem.objects.values("minutes", "decision").get(pk=item.pk)
    changed = [name for name, value in [("minutes", minutes), ("decision", decision)] if stored[name] != value]
    if not changed:
        return item
    item.minutes, item.decision = minutes, decision
    item.save(update_fields=["minutes", "decision", "updated_at"])
    record_audit_log(item.meeting, user, action=AuditLog.Action.UPDATE, request=request,
                     custom_summary=f"{' and '.join(changed).capitalize()} changed: {item.title}")
    return item


@transaction.atomic
def mark_held(meeting, user, *, attendees, guests="", request=None):
    """The meeting happened: record who was there and ask council to approve the minutes.

    Returns None when the meeting was no longer planned (a double submit): nothing is done twice.
    """
    meeting = _lock(meeting, Meeting.Status.PLANNED)
    if meeting is None:
        return None
    meeting.status, meeting.held_at, meeting.guests = Meeting.Status.HELD, timezone.now(), guests.strip()
    meeting.save()
    meeting.attendees.set(attendees)

    record_audit_log(meeting, user, action=AuditLog.Action.STATUS_CHANGE, request=request,
                     custom_summary="Meeting held; minutes in draft")
    meeting.reset_initial_state()
    council = [e for e in member_emails(meeting.strata, role=Membership.Role.COUNCIL) if e != user.email]
    transaction.on_commit(lambda: emails.send("minutes_ready", council, {"meeting": meeting, "recorded_by": user}))
    return meeting


@transaction.atomic
def approve_minutes(meeting, user, request=None):
    """Council approves: the minutes lock and each decision is posted to its issue or case timeline.

    Returns None when the minutes weren't awaiting approval any more (a double submit).
    """
    meeting = _lock(meeting, Meeting.Status.HELD)
    if meeting is None:
        return None
    now = timezone.now()
    meeting.status, meeting.approved_at, meeting.approved_by = Meeting.Status.APPROVED, now, user
    meeting.save()

    label = f"{meeting.get_kind_display()} on {_day(meeting)}"
    for item in meeting.items.exclude(decision="").select_related("issue", "incident"):
        if item.issue_id:
            IssueUpdate.objects.create(issue=item.issue, author=user, kind=IssueUpdate.Kind.COMMENT,
                                       body=f"Decided at the {label} (minutes approved): {item.decision}")
            Issue.objects.filter(pk=item.issue_id).update(last_activity_at=now)
        if item.incident_id:
            IncidentEvent.objects.create(
                incident=item.incident, created_by=user, event_type=IncidentEvent.EventType.NOTE,
                description=f"Decided at the {label} (in camera, minutes approved): {item.decision}")

    record_audit_log(meeting, user, action=AuditLog.Action.STATUS_CHANGE, request=request,
                     custom_summary="Minutes approved")
    meeting.reset_initial_state()
    return meeting


def cancel_meeting(meeting, user, request=None):
    meeting.status = Meeting.Status.CANCELLED
    meeting.save()
    record_audit_log(meeting, user, action=AuditLog.Action.STATUS_CHANGE, request=request,
                     custom_summary="Meeting cancelled")
    meeting.reset_initial_state()
    return meeting


def _lock(meeting, expected_status):
    """Re-read the meeting under a row lock; None if another request already moved it on."""
    locked = Meeting.objects.select_for_update().get(pk=meeting.pk)
    return locked if locked.status == expected_status else None


def _issue_brief(issue):
    owner = (issue.assigned_to.get_full_name() or issue.assigned_to.email) if issue.assigned_to else "nobody"
    brief = f"{issue.get_status_display()}. Owner: {owner}."
    if issue.due_date:
        brief += f" Fix by {issue.due_date:%b} {issue.due_date.day}."
    return brief


def _case_label(case):
    return f"Unit {case.unit_number}, {case.title}" if case.unit_number else case.title


def _day(meeting):
    when = timezone.localtime(meeting.starts_at)
    return f"{when:%b} {when.day}, {when.year}"
