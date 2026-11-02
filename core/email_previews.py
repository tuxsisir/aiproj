"""Sample data for the staff email preview page. Unsaved objects only: previewing never touches the database."""
import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone

from dockets.models import Bylaw, Incident
from documents.models import Document
from inbox.models import InboundEmail
from issues.models import Issue
from meetings.models import AgendaItem, Meeting
from stratas.models import Membership, StrataPlan


def sample_context():
    user = get_user_model()(email="sara@example.com", first_name="Sara", last_name="Gill")
    strata = StrataPlan(plan_number="EPS 1234", name="Kingsview Manor")
    membership = Membership(
        user=user, strata=strata, role=Membership.Role.COUNCIL,
        position=Membership.Position.TREASURER, unit_number="304",
    )
    bylaw = Bylaw(strata=strata, code="3(4)", title="Quiet Enjoyment & Nuisance", standard_fine=200)
    incident = Incident(
        strata=strata, bylaw=bylaw, title="Loud music after 11pm", unit_number="1204",
        description="Repeated loud music from unit 1204 after 11pm on Friday and Saturday.",
        status=Incident.Status.RESOLVED_FINED,
    )
    document = Document(
        strata=strata, title="Bylaws (consolidated 2024)",
        summary={
            "overview": "Consolidated strata bylaws covering use of property, pets, parking and rentals.",
            "topics": [{"name": "Parking", "points": []}, {"name": "Pets", "points": []}, {"name": "Rentals", "points": []}],
        },
    )
    email = InboundEmail(
        strata=strata, subject="Fwd: Water coming through ceiling",
        summary={
            "title": "Ceiling leak in unit 304 from unit 404",
            "summary": "Water has been dripping from the bathroom ceiling of 304 since this morning. "
                       "The manager booked ABC Plumbing for Tuesday 9am and asked council to approve up to $800.",
            "category": "Maintenance & Repairs",
            "urgency": "urgent",
            "action_items": [
                {"task": "Approve emergency plumber call-out up to $800", "owner": "Council", "due": "Before Tuesday"},
                {"task": "Arrange access to unit 404", "owner": "Strata manager", "due": ""},
            ],
            "suggested_next_step": "Approve the call-out today and ask 404 to check their bathroom for leaks.",
        },
    )
    issue = Issue(
        strata=strata, title="Storage room 5 door doesn't latch", location="Parkade P1, storage room 5",
        category=Issue.Category.SECURITY, priority=Issue.Priority.HIGH, raised_by=user, assigned_to=user,
        description="The strike plate is bent and the door swings open. Two lockers were entered last month.",
    )
    meeting = Meeting(
        strata=strata, kind=Meeting.Kind.COUNCIL, location="Amenity room", created_by=user,
        starts_at=timezone.now() + datetime.timedelta(days=10),
    )
    items = [AgendaItem(title=t) for t in ["Call to order", "Financial report", f"Issue: {issue.title}"]]
    items.append(AgendaItem(title="Enforcement: Unit 1204, loud music", in_camera=True))
    return {
        "user": user,
        "meeting": meeting,
        "items": items,
        "recorded_by": user,
        "issue": issue,
        "assigned_by": user,
        "membership": membership,
        "incident": incident,
        "document": document,
        "email": email,
        "response_url": "https://usecivicdesk.com/dockets/respond/sample-token/",
        "password_reset_url": "https://usecivicdesk.com/accounts/password/reset/key/sample/",
        "signup_url": "https://usecivicdesk.com/accounts/signup/",
    }
