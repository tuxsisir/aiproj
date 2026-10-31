from django.test import TestCase
from django.urls import reverse

from core.testing import make_membership, make_strata, make_user
from stratas.models import Membership
from .models import CouncilVote, Incident


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
        self.assertTrue(Incident.objects.filter(strata=self.strata, title="Bike in lobby").exists())

    def test_manager_cannot_log_docket(self):
        manager = make_membership(make_user(), self.strata, role=Membership.Role.MANAGER)
        self.client.force_login(manager.user)
        self.client.post(reverse("dockets:incident_create"), {
            "title": "Nope", "incident_type": Incident.Type.BYLAW, "description": "x",
        })
        self.assertFalse(Incident.objects.exists())
