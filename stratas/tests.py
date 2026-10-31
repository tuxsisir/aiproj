from django.core import mail
from django.test import TestCase
from django.urls import reverse

from core.testing import make_membership, make_strata, make_user
from dockets.models import Bylaw, Incident
from .models import Membership, StrataPlan

Role, Position, Status = Membership.Role, Membership.Position, Membership.Status


class OnboardingTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.strata = make_strata("EPS100")

    def post_onboarding(self, **data):
        return self.client.post(reverse("onboarding"), data)

    def test_user_without_membership_is_sent_to_onboarding(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("onboarding"))

    def test_council_member_joining_existing_building_is_pending(self):
        response = self.post_onboarding(
            persona=Role.COUNCIL, strata_id=self.strata.id, position=Position.TREASURER, unit_number="304"
        )
        self.assertRedirects(response, reverse("membership_pending"))
        membership = Membership.objects.get(user=self.user)
        self.assertEqual(membership.status, Status.PENDING)
        self.assertEqual(membership.role, Role.COUNCIL)
        self.assertEqual(membership.position, Position.TREASURER)
        self.assertEqual(membership.title, "Treasurer")

    def test_pending_user_cannot_reach_dashboard(self):
        make_membership(self.user, self.strata, status=Status.PENDING)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("membership_pending"))
        self.assertRedirects(self.client.get(reverse("onboarding")), reverse("membership_pending"))
        self.assertContains(self.client.get(reverse("membership_pending")), "EPS100")

    def test_manager_registering_new_building(self):
        response = self.post_onboarding(
            persona=Role.MANAGER, plan_number="eps 1234", name="Kingsview", brokerage_name="Acme Mgmt"
        )
        self.assertRedirects(response, reverse("membership_pending"))
        strata = StrataPlan.objects.get(plan_number="EPS1234")
        self.assertEqual(strata.created_by, self.user)
        self.assertTrue(Bylaw.objects.filter(strata=strata).exists())
        self.assertFalse(Incident.objects.filter(strata=strata).exists())
        membership = Membership.objects.get(user=self.user, strata=strata)
        self.assertEqual((membership.role, membership.position, membership.status), (Role.MANAGER, "", Status.PENDING))
        self.user.refresh_from_db()
        self.assertEqual(self.user.brokerage_name, "Acme Mgmt")

    def test_cannot_self_assign_unknown_role_or_position(self):
        self.post_onboarding(persona="ADMIN", strata_id=self.strata.id, position=Position.PRESIDENT, unit_number="1")
        self.post_onboarding(persona=Role.COUNCIL, strata_id=self.strata.id, position="OWNER", unit_number="1")
        self.assertFalse(Membership.objects.exists())

    def test_council_requires_position_and_unit(self):
        response = self.post_onboarding(persona=Role.COUNCIL, strata_id=self.strata.id)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Membership.objects.exists())

    def test_invalid_or_duplicate_plan_number_rejected(self):
        self.post_onboarding(persona=Role.MANAGER, plan_number="XYZ 1", name="Bad", brokerage_name="A")
        self.post_onboarding(persona=Role.MANAGER, plan_number="EPS 100", name="Dup", brokerage_name="A")
        self.assertEqual(StrataPlan.objects.count(), 1)
        self.assertFalse(Membership.objects.exists())

    def test_platform_admins_are_emailed_about_requests(self):
        make_user("admin@example.com", is_superuser=True, is_staff=True)
        self.post_onboarding(persona=Role.COUNCIL, strata_id=self.strata.id, position=Position.SECRETARY, unit_number="2")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["admin@example.com"])

    def test_active_council_member_cannot_onboard_again(self):
        make_membership(self.user, self.strata)
        self.assertRedirects(self.client.get(reverse("onboarding")), reverse("dashboard"))

    def test_active_manager_can_request_another_building(self):
        make_membership(self.user, self.strata, role=Role.MANAGER)
        other = make_strata("EPS200")
        self.post_onboarding(persona=Role.MANAGER, strata_id=other.id, brokerage_name="Acme")
        self.assertEqual(Membership.objects.get(user=self.user, strata=other).status, Status.PENDING)
        # Still working in the approved building meanwhile.
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_rejected_user_can_reapply(self):
        make_membership(self.user, self.strata, status=Status.REJECTED)
        self.post_onboarding(persona=Role.COUNCIL, strata_id=self.strata.id, position=Position.MEMBER_AT_LARGE, unit_number="5")
        self.assertEqual(Membership.objects.get(user=self.user).status, Status.PENDING)


class AdminApprovalTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", is_superuser=True, is_staff=True)
        self.user = make_user("member@example.com")
        self.strata = make_strata()
        self.membership = make_membership(self.user, self.strata, status=Status.PENDING, position=Position.TREASURER)
        self.client.force_login(self.admin)

    def run_action(self, action):
        return self.client.post(
            reverse("admin:stratas_membership_changelist"),
            {"action": action, "_selected_action": [self.membership.pk]},
        )

    def test_approve_activates_membership_and_emails_member(self):
        self.run_action("approve_selected")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, Status.ACTIVE)
        self.assertEqual(self.membership.reviewed_by, self.admin)
        self.assertIsNotNone(self.membership.reviewed_at)
        self.assertEqual(mail.outbox[-1].to, ["member@example.com"])

        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_reject_sends_member_back_to_onboarding(self):
        self.run_action("reject_selected")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, Status.REJECTED)
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("onboarding"))

    def test_actions_only_touch_pending_memberships(self):
        self.membership.status = Status.INACTIVE
        self.membership.save()
        self.run_action("approve_selected")
        self.membership.refresh_from_db()
        self.assertEqual(self.membership.status, Status.INACTIVE)


class TenantIsolationTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.home = make_strata()
        self.other = make_strata()
        make_membership(self.user, self.home)
        self.client.force_login(self.user)

    def test_cannot_open_incident_from_another_building(self):
        incident = Incident.objects.create(strata=self.other, title="x", description="y")
        response = self.client.get(reverse("dockets:incident_detail", args=[incident.pk]))
        self.assertEqual(response.status_code, 404)

    def test_session_cannot_point_at_a_pending_building(self):
        make_membership(self.user, self.other, status=Status.PENDING)
        session = self.client.session
        session["active_strata_id"] = str(self.other.id)
        session.save()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.wsgi_request.strata, self.home)

    def test_members_list_shows_only_active_members(self):
        make_membership(make_user("pending@example.com"), self.home, status=Status.PENDING)
        response = self.client.get(reverse("building_members"))
        emails = [m.user.email for m in response.context["memberships"]]
        self.assertNotIn("pending@example.com", emails)
        self.assertIn(self.user.email, emails)


class SwitchAndLeaveTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.a = make_strata()
        self.b = make_strata()
        self.client.force_login(self.user)

    def test_manager_can_switch_buildings(self):
        make_membership(self.user, self.a, role=Role.MANAGER)
        make_membership(self.user, self.b, role=Role.MANAGER)
        self.client.post(reverse("switch_strata", args=[self.b.id]))
        self.assertEqual(self.client.session["active_strata_id"], str(self.b.id))

    def test_council_member_cannot_switch(self):
        make_membership(self.user, self.a)
        make_membership(self.user, self.b)
        session = self.client.session
        session["active_strata_id"] = str(self.a.id)
        session.save()
        self.client.post(reverse("switch_strata", args=[self.b.id]))
        self.assertEqual(self.client.session["active_strata_id"], str(self.a.id))

    def test_switch_ignores_external_referer(self):
        make_membership(self.user, self.a, role=Role.MANAGER)
        response = self.client.post(reverse("switch_strata", args=[self.a.id]), HTTP_REFERER="https://evil.example/")
        self.assertRedirects(response, reverse("dashboard"))

    def test_manager_leaving_deactivates_instead_of_deleting(self):
        membership = make_membership(self.user, self.a, role=Role.MANAGER)
        response = self.client.post(reverse("leave_strata", args=[self.a.id]))
        self.assertRedirects(response, reverse("onboarding"))
        membership.refresh_from_db()
        self.assertEqual(membership.status, Status.INACTIVE)
