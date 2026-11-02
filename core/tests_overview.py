import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import overview
from core.testing import make_membership, make_strata, make_user
from dockets.models import CouncilVote, Incident, IncidentEvent
from inbox.models import InboundEmail
from schedule.models import KeyDate
from stratas.models import Membership

Status = Incident.Status


def at(days):
    return timezone.now() + datetime.timedelta(days=days)


class OverviewTestCase(TestCase):
    def setUp(self):
        self.strata = make_strata(name="Demo")
        self.council = make_membership(make_user(), self.strata)
        self.manager = make_membership(make_user(), self.strata, role=Membership.Role.MANAGER)

    def case(self, status, strata=None, **fields):
        return Incident.objects.create(strata=strata or self.strata, title=fields.pop("title", "Overstay"),
                                       description="d", unit_number="305", status=status, **fields)

    def titles(self, membership):
        return [n.title for n in overview.needs_you(membership)]


class NeedsYouTests(OverviewTestCase):
    def test_new_complaint_is_on_the_manager_and_visible_to_council(self):
        self.case(Status.IN_REVIEW)
        self.assertEqual(self.titles(self.manager), ["Review complaint: Overstay"])
        self.assertEqual(self.titles(self.council), ["Waiting on the manager: Overstay"])

    def test_vote_needed_until_this_member_has_voted(self):
        case = self.case(Status.VOTING_OPEN)
        self.assertEqual(self.titles(self.council), ["Your vote is needed: Overstay"])
        self.assertEqual(self.titles(self.manager), ["Council vote in progress: Overstay"])

        CouncilVote.objects.create(incident=case, member=self.council, approve_fine=True)
        self.assertEqual(self.titles(self.council), [])  # the only council member has voted

    def test_missed_owner_deadline_is_overdue_and_listed_first(self):
        self.case(Status.IN_REVIEW, title="Newer")
        self.case(Status.NOTICE_ISSUED, title="Silent owner", statutory_deadline=at(-2))

        needs = overview.needs_you(self.manager)
        self.assertEqual((needs[0].severity, needs[0].title), ("overdue", "No response from the owner: Silent owner"))

    def test_owner_deadline_within_three_days_is_coming_up(self):
        self.case(Status.NOTICE_ISSUED, statutory_deadline=at(2))
        [need] = overview.needs_you(self.council)
        self.assertEqual(need.severity, "soon")

    def test_authorized_fine_waits_on_the_manager_until_sent(self):
        case = self.case(Status.RESOLVED_FINED)
        self.assertEqual(self.titles(self.manager), ["Send the fine notice: Overstay"])
        self.assertEqual(self.titles(self.council), ["Fine notice not sent yet: Overstay"])

        IncidentEvent.objects.create(incident=case, event_type=IncidentEvent.EventType.FINE_DISPATCHED, description="sent")
        self.assertEqual(self.titles(self.manager), [])

    def test_urgent_emails_and_key_dates_in_the_next_two_weeks(self):
        InboundEmail.objects.create(strata=self.strata, from_email="a@example.com", subject="Gate",
                                    summary={"title": "Gate stuck open", "urgency": "high"}, status="READY")
        InboundEmail.objects.create(strata=self.strata, from_email="b@example.com", subject="Hello",
                                    summary={"title": "Thanks", "urgency": "low"}, status="READY")
        today = timezone.localdate()
        KeyDate.objects.create(strata=self.strata, title="AGM", date=today + datetime.timedelta(days=10))
        KeyDate.objects.create(strata=self.strata, title="Far away", date=today + datetime.timedelta(days=40))

        self.assertEqual(sorted(self.titles(self.council)), ["AGM", "Urgent email: Gate stuck open"])

    def test_never_includes_another_buildings_items(self):
        other = make_strata()
        self.case(Status.IN_REVIEW, strata=other)
        self.case(Status.VOTING_OPEN, strata=other)
        KeyDate.objects.create(strata=other, title="Their AGM", date=timezone.localdate())
        self.assertEqual(self.titles(self.manager), [])
        self.assertEqual(self.titles(self.council), [])


class PortfolioAndPillarTests(OverviewTestCase):
    def test_portfolio_counts_only_the_managers_buildings(self):
        second = make_strata(name="Second")
        make_membership(self.manager.user, second, role=Membership.Role.MANAGER)
        not_mine = make_strata(name="Not mine")
        self.case(Status.IN_REVIEW)
        self.case(Status.NOTICE_ISSUED, strata=second, statutory_deadline=at(-1))
        self.case(Status.IN_REVIEW, strata=not_mine)

        rows = {b.name: (b.new_cases, b.overdue, b.voting) for b in overview.portfolio(self.manager.user)}
        self.assertEqual(rows, {"Demo": (1, 0, 0), "Second": (0, 1, 0)})

    def test_portfolio_skips_inactive_and_council_memberships(self):
        make_membership(self.manager.user, make_strata(name="Left"), role=Membership.Role.MANAGER,
                        status=Membership.Status.INACTIVE)
        make_membership(self.manager.user, make_strata(name="Pending"), role=Membership.Role.MANAGER,
                        status=Membership.Status.PENDING)
        make_membership(self.manager.user, make_strata(name="Own unit"), role=Membership.Role.COUNCIL)

        self.assertEqual([b.name for b in overview.portfolio(self.manager.user)], ["Demo"])

    def test_pillar_numbers(self):
        self.case(Status.IN_REVIEW)
        self.case(Status.VOTING_OPEN)
        self.case(Status.RESOLVED_DISMISSED)
        self.case(Status.NOTICE_ISSUED, statutory_deadline=at(-1))

        cases = overview.pillars(self.strata)["cases"]
        self.assertEqual(cases, {"open": 3, "new": 1, "voting": 1, "overdue": 1})


class OnYouTests(OverviewTestCase):
    def test_counts_only_what_this_person_can_move(self):
        self.case(Status.NOTICE_ISSUED, statutory_deadline=at(-2))  # missed deadline: the manager's to move
        InboundEmail.objects.create(strata=self.strata, from_email="a@example.com", subject="Gate",
                                    summary={"title": "Gate", "urgency": "urgent"}, status="READY")

        council = overview.needs_you(self.council)
        manager = overview.needs_you(self.manager)

        self.assertEqual([n.on_you for n in council], [False, False])  # visible, but not counted
        self.assertEqual([(n.severity, n.on_you) for n in manager], [("overdue", True), ("action", False)])


class DashboardViewTests(OverviewTestCase):
    def test_logged_out_visitor_is_sent_to_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("account_login"), response["Location"])

    def test_council_view(self):
        self.case(Status.VOTING_OPEN)
        self.client.force_login(self.council.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Your vote is needed: Overstay")
        self.assertContains(response, "1 thing needs you")
        self.assertNotContains(response, "Your buildings")

    def test_manager_view_has_portfolio(self):
        self.client.force_login(self.manager.user)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Your buildings")
        self.assertContains(response, "Nothing is waiting on you")
        self.assertContains(response, "All caught up.")

    def test_recent_activity_is_this_building_only(self):
        mine = self.case(Status.NOTICE_ISSUED, title="Mine")
        theirs = self.case(Status.NOTICE_ISSUED, strata=make_strata(), title="Theirs")
        for case in (mine, theirs):
            IncidentEvent.objects.create(incident=case, event_type=IncidentEvent.EventType.NOTE, description="n")
        self.client.force_login(self.council.user)

        response = self.client.get(reverse("dashboard"))

        self.assertContains(response, "Manager / Council Note: Mine")
        self.assertNotContains(response, "Theirs")
