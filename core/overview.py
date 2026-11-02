"""
The Overview page: what needs this person now, how each pillar stands, what's coming and what just happened.

Plain data in, plain data out, so the view stays thin and each part is testable on its own.
Role matters: council members see what waits on their vote; the manager sees what waits on them; each also
sees what is stuck with the other side, because silence must be visible.
"""
import datetime
from dataclasses import dataclass

from django.db.models import Count, Exists, OuterRef, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.timesince import timesince

from dockets.models import CouncilVote, Incident, IncidentEvent
from documents.models import Document
from schedule import feed
from stratas.models import Membership, StrataPlan

CLOSED = [Incident.Status.RESOLVED_FINED, Incident.Status.RESOLVED_DISMISSED]
URGENT_EMAIL = ["high", "urgent"]
LOOKAHEAD_DAYS = 14

# Most urgent first.
SEVERITY_ORDER = {"overdue": 0, "action": 1, "soon": 2, "waiting": 3}


@dataclass(frozen=True)
class Need:
    severity: str  # "overdue", "action" (on you), "soon", "waiting" (on someone else)
    title: str
    detail: str
    url: str
    pillar: str
    sort_date: datetime.date
    on_you: bool = False  # counted in "N things need you": only what this person can actually move forward


def needs_you(membership, today=None):
    """Everything that needs attention in this building, as seen by this member, most urgent first."""
    today = today or timezone.localdate()
    strata, is_manager = membership.strata, membership.is_manager
    open_cases = strata.incidents.exclude(status__in=CLOSED)
    needs = []

    for case in open_cases.filter(status=Incident.Status.IN_REVIEW).order_by("created_at"):
        age = f"raised {timesince(case.created_at)} ago"
        if is_manager:
            needs.append(_need("action", f"Review complaint: {case.title}", f"{_unit(case)}{age}. Send the notice "
                               "or close it.", case, _day(case.created_at), on_you=True))
        else:
            needs.append(_need("waiting", f"Waiting on the manager: {case.title}", f"{_unit(case)}{age}, "
                               "no notice sent yet.", case, _day(case.created_at)))

    council_size = strata.memberships.active().council().count()
    my_vote = CouncilVote.objects.filter(incident=OuterRef("pk"), member=membership)
    voting = (open_cases.filter(status=Incident.Status.VOTING_OPEN)
              .annotate(vote_count=Count("votes"), voted=Exists(my_vote)).order_by("updated_at"))
    for case in voting:
        tally = f"{case.vote_count} of {council_size} council votes in."
        if membership.is_council and not case.voted:
            needs.append(_need("action", f"Your vote is needed: {case.title}", f"{_unit(case)}{tally}",
                               case, _day(case.updated_at), url=reverse("dockets:voting_center"), on_you=True))
        elif case.vote_count < council_size:
            needs.append(_need("waiting", f"Council vote in progress: {case.title}", f"{_unit(case)}{tally}",
                               case, _day(case.updated_at)))

    for case in open_cases.filter(status=Incident.Status.NOTICE_ISSUED, statutory_deadline__isnull=False):
        deadline = timezone.localtime(case.statutory_deadline).date()
        # Missed deadlines are the manager's to move; council sees them but can't act yet (no next-step flow).
        status = feed.deadline_status(deadline, today)
        if status == "overdue":
            needs.append(_need("overdue", f"No response from the owner: {case.title}",
                               f"{_unit(case)}reply was due {_md(deadline)}. Decide the next step.", case, deadline,
                               on_you=is_manager))
        elif status == "soon":
            needs.append(_need("soon", f"Owner response due: {case.title}",
                               f"{_unit(case)}due {_md(deadline)}.", case, deadline))

    fine_sent = IncidentEvent.objects.filter(incident=OuterRef("pk"), event_type=IncidentEvent.EventType.FINE_DISPATCHED)
    for case in strata.incidents.filter(status=Incident.Status.RESOLVED_FINED).annotate(sent=Exists(fine_sent)):
        if case.sent:
            continue
        if is_manager:
            needs.append(_need("action", f"Send the fine notice: {case.title}",
                               f"{_unit(case)}council voted to fine.", case, _day(case.updated_at), on_you=True))
        else:
            needs.append(_need("waiting", f"Fine notice not sent yet: {case.title}",
                               f"{_unit(case)}council voted to fine; waiting on the manager.", case, _day(case.updated_at)))

    # Shown for 14 days; not counted as "on you" because an email can't be marked handled yet.
    for email in strata.inbound_emails.filter(summary__urgency__in=URGENT_EMAIL,
                                              received_at__date__gte=today - datetime.timedelta(days=LOOKAHEAD_DAYS)):
        needs.append(Need("action" if is_manager else "waiting", f"Urgent email: {email.title}",
                          email.summary.get("suggested_next_step", ""),
                          reverse("inbox:detail", args=[email.pk]), "Forwarded email", _day(email.received_at)))

    for event in feed.key_date_events(strata, today, today + datetime.timedelta(days=LOOKAHEAD_DAYS)):
        when = "today" if event.date == today else f"in {timesince(today, event.date)}"
        needs.append(Need("soon", event.title, f"{event.detail} · {_md(event.date)} ({when})",
                          event.url, "Calendar", event.date))

    return sorted(needs, key=lambda n: (SEVERITY_ORDER[n.severity], n.sort_date))


def pillars(strata, today=None):
    """One line of live numbers per pillar."""
    today = today or timezone.localdate()
    cases = strata.incidents.aggregate(
        open=Count("id", filter=~Q(status__in=CLOSED)),
        new=Count("id", filter=Q(status=Incident.Status.IN_REVIEW)),
        voting=Count("id", filter=Q(status=Incident.Status.VOTING_OPEN)),
        overdue=Count("id", filter=Q(status=Incident.Status.NOTICE_ISSUED, statutory_deadline__date__lt=today)),
    )
    upcoming = feed.events_between(strata, today, today + datetime.timedelta(days=30))
    docs = strata.documents.aggregate(total=Count("id"),
                                      ready=Count("id", filter=Q(summary_status=Document.SummaryStatus.READY)))
    since = today - datetime.timedelta(days=30)
    emails = strata.inbound_emails.aggregate(
        recent=Count("id", filter=Q(received_at__date__gte=since)),
        urgent=Count("id", filter=Q(summary__urgency__in=URGENT_EMAIL, received_at__date__gte=since)),
    )
    return {
        "cases": cases,
        "upcoming": upcoming,
        "next_event": upcoming[0] if upcoming else None,
        "documents": docs,
        "questions": strata.document_questions.count(),
        "emails": emails,
    }


def recent_activity(strata, limit=8):
    """The latest things that happened in the building, across pillars."""
    items = []
    for event in IncidentEvent.objects.filter(incident__strata=strata).select_related("incident", "created_by") \
            .order_by("-occurred_at")[:limit]:
        who = event.created_by.get_full_name() if event.created_by else "Owner"
        items.append({"when": event.occurred_at, "pillar": "Enforcement", "who": who,
                      "text": f"{event.get_event_type_display()}: {event.incident.title}",
                      "url": reverse("dockets:incident_detail", args=[event.incident_id])})
    for email in strata.inbound_emails.select_related("forwarded_by").order_by("-received_at")[:limit]:
        who = email.forwarded_by.get_full_name() if email.forwarded_by else email.from_email
        items.append({"when": email.received_at, "pillar": "Forwarded email", "who": who,
                      "text": f"Forwarded: {email.title}", "url": reverse("inbox:detail", args=[email.pk])})
    for doc in strata.documents.select_related("uploaded_by").order_by("-created_at")[:limit]:
        who = doc.uploaded_by.get_full_name() if doc.uploaded_by else ""
        items.append({"when": doc.created_at, "pillar": "Documents", "who": who,
                      "text": f"Uploaded {doc.title}", "url": reverse("documents:detail", args=[doc.pk])})
    for question in strata.document_questions.select_related("asked_by").order_by("-created_at")[:limit]:
        who = question.asked_by.get_full_name() if question.asked_by else ""
        items.append({"when": question.created_at, "pillar": "Ask", "who": who,
                      "text": f"Asked: {question.question}", "url": reverse("documents:question", args=[question.pk])})
    return sorted(items, key=lambda i: i["when"], reverse=True)[:limit]


def portfolio(user, today=None):
    """For a manager: every building they manage with what needs action there (one query)."""
    today = today or timezone.localdate()
    managed = Membership.objects.active().managers().filter(user=user).values("strata_id")
    return (StrataPlan.objects.filter(pk__in=managed)
            .annotate(
                new_cases=Count("incidents", filter=Q(incidents__status=Incident.Status.IN_REVIEW), distinct=True),
                overdue=Count("incidents", filter=Q(incidents__status=Incident.Status.NOTICE_ISSUED,
                                                    incidents__statutory_deadline__date__lt=today), distinct=True),
                voting=Count("incidents", filter=Q(incidents__status=Incident.Status.VOTING_OPEN), distinct=True),
            ).order_by("name"))


def _need(severity, title, detail, case, sort_date, url=None, on_you=False):
    return Need(severity, title, detail, url or reverse("dockets:incident_detail", args=[case.pk]),
                "Enforcement", sort_date, on_you)


def _md(day):
    return f"{day:%b} {day.day}"  # "Oct 27" (portable; %-d isn't available everywhere)


def _unit(case):
    return f"Unit {case.unit_number} · " if case.unit_number else ""


def _day(value):
    return timezone.localtime(value).date()
