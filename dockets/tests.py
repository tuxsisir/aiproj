from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from core.models import AuditLog
from core.testing import make_membership, make_strata, make_user
from stratas.models import Membership
from .models import CouncilVote, Incident, IncidentEvent


class CouncilVoteTests(TestCase):
    def setUp(self):
        self.strata = make_strata()
        self.alice = make_membership(make_user(), self.strata)
        self.bob = make_membership(make_user(), self.strata)
        self.incident = Incident.objects.create(
            strata=self.strata, title="Noise", description="Loud", status=Incident.Status.VOTING_OPEN
        )

    def vote(self, membership, approve):
        self.client.force_login(membership.user)
        return self.client.post(
            reverse("dockets:cast_council_vote", args=[self.incident.pk]),
            {"approve_fine": "true" if approve else "false"},
        )

    def test_quorum_ignores_inactive_and_pending_council_members(self):
        make_membership(make_user(), self.strata, status=Membership.Status.INACTIVE)
        make_membership(make_user(), self.strata, status=Membership.Status.PENDING)
        self.vote(self.alice, True)
        self.vote(self.bob, True)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.RESOLVED_FINED)
        actions = list(AuditLog.objects.values_list("action", flat=True))
        self.assertEqual(actions.count(AuditLog.Action.VOTE_CAST), 2)
        self.assertIn(AuditLog.Action.STATUS_CHANGE, actions)

    def test_manager_cannot_vote(self):
        manager = make_membership(make_user(), self.strata, role=Membership.Role.MANAGER)
        self.vote(manager, True)
        self.assertFalse(CouncilVote.objects.exists())


class IncidentCreateTests(TestCase):
    def setUp(self):
        self.strata = make_strata()

    def test_council_member_can_log_docket(self):
        council = make_membership(make_user(), self.strata, position=Membership.Position.TREASURER)
        self.client.force_login(council.user)
        self.client.post(reverse("dockets:incident_create"), {
            "title": "Bike in lobby", "incident_type": Incident.Type.BYLAW, "description": "Again",
        })
        incident = Incident.objects.get(strata=self.strata, title="Bike in lobby")
        self.assertTrue(AuditLog.objects.filter(object_id=str(incident.pk), action=AuditLog.Action.CREATE).exists())

    def test_manager_cannot_log_docket(self):
        manager = make_membership(make_user(), self.strata, role=Membership.Role.MANAGER)
        self.client.force_login(manager.user)
        self.client.post(reverse("dockets:incident_create"), {
            "title": "Nope", "incident_type": Incident.Type.BYLAW, "description": "x",
        })
        self.assertFalse(Incident.objects.exists())


class LogIncidentEventTests(TestCase):
    def setUp(self):
        self.strata = make_strata()
        self.member = make_membership(make_user(), self.strata)
        self.incident = Incident.objects.create(
            strata=self.strata, title="Noise", description="Loud", status=Incident.Status.NOTICE_ISSUED,
            statutory_deadline=timezone.now() + timezone.timedelta(days=14),
        )
        self.client.force_login(self.member.user)
        self.url = reverse("dockets:log_incident_event", args=[self.incident.pk])

    def test_member_can_add_note(self):
        self.client.post(self.url, {"event_type": IncidentEvent.EventType.NOTE, "description": "Called owner"})
        event = IncidentEvent.objects.get(incident=self.incident)
        self.assertEqual((event.event_type, event.created_by), (IncidentEvent.EventType.NOTE, self.member.user))

    def test_member_cannot_fake_owner_statement_or_fine(self):
        for event_type in (IncidentEvent.EventType.OWNER_STATEMENT, IncidentEvent.EventType.FINE_DISPATCHED):
            self.client.post(self.url, {"event_type": event_type, "description": "fake"})
        self.assertFalse(IncidentEvent.objects.exists())

    def test_description_is_required(self):
        self.client.post(self.url, {"event_type": IncidentEvent.EventType.NOTE})
        self.assertFalse(IncidentEvent.objects.exists())

    def test_owner_can_still_respond_after_member_notes(self):
        self.client.post(self.url, {"event_type": IncidentEvent.EventType.NOTE, "description": "Note"})
        self.client.logout()
        self.client.post(
            reverse("dockets:owner_response_portal", args=[self.incident.owner_token]),
            {"response_type": "WRITTEN", "statement": "It was my TV"},
        )
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status, Incident.Status.VOTING_OPEN)
        self.assertTrue(self.incident.events.filter(event_type=IncidentEvent.EventType.OWNER_STATEMENT).exists())

    def test_cannot_log_on_another_buildings_incident(self):
        other = Incident.objects.create(strata=make_strata(), title="x", description="y")
        response = self.client.post(
            reverse("dockets:log_incident_event", args=[other.pk]),
            {"event_type": IncidentEvent.EventType.NOTE, "description": "x"},
        )
        self.assertEqual(response.status_code, 404)



@override_settings(SITE_URL="https://app.example.com")
class DocketEmailTests(TestCase):
    def setUp(self):
        self.strata = make_strata()
        self.council = make_membership(make_user("council@example.com"), self.strata)
        self.manager = make_membership(make_user("manager@example.com"), self.strata, role=Membership.Role.MANAGER)

    def test_new_docket_notifies_managers(self):
        self.client.force_login(self.council.user)
        self.client.post(reverse("dockets:incident_create"), {
            "title": "Bike in lobby", "incident_type": Incident.Type.BYLAW, "description": "Again",
        })
        self.assertEqual([m.to for m in mail.outbox], [["manager@example.com"]])

    def test_s135_notice_links_to_owner_portal_on_site_url(self):
        incident = Incident.objects.create(
            strata=self.strata, title="Noise", description="Loud", unit_number="304", recipient_email="owner@example.com"
        )
        self.client.force_login(self.manager.user)
        self.client.post(reverse("dockets:dispatch_section_135", args=[incident.pk]))
        notice = mail.outbox[-1]
        self.assertEqual(notice.to, ["owner@example.com"])
        self.assertIn(f"https://app.example.com/dockets/respond/{incident.owner_token}/", notice.body)

    def test_owner_response_notifies_council(self):
        incident = Incident.objects.create(
            strata=self.strata, title="Noise", description="Loud", status=Incident.Status.NOTICE_ISSUED,
            statutory_deadline=timezone.now() + timezone.timedelta(days=14),
        )
        self.client.post(
            reverse("dockets:owner_response_portal", args=[incident.owner_token]),
            {"response_type": "WRITTEN", "statement": "Not me"},
        )
        self.assertEqual([m.to for m in mail.outbox], [["council@example.com"]])
        self.assertIn("Council vote needed", mail.outbox[0].subject)
