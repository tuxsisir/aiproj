import datetime

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import overview
from core.models import AuditLog
from core.testing import make_membership, make_strata, make_user
from dockets.models import Incident
from inbox.models import InboundEmail
from schedule import feed
from stratas.models import Membership
from .models import Issue, IssueUpdate

Status = Issue.Status


class IssueTestCase(TestCase):
    def setUp(self):
        self.strata = make_strata()
        self.council = make_membership(make_user(first_name="Sara"), self.strata)
        self.manager = make_membership(make_user(first_name="Mike"), self.strata, role=Membership.Role.MANAGER)
        self.client.force_login(self.council.user)

    def issue(self, strata=None, **fields):
        fields = {"title": "Storage door doesn't latch", "raised_by": self.council.user, **fields}
        return Issue.objects.create(strata=strata or self.strata, **fields)

    def post_update(self, issue, **data):
        data = {"status": issue.status, "assigned_to": issue.assigned_to_id or "", "due_date": "",
                "vendor": issue.vendor, "comment": "", "outcome": "", **data}
        return self.client.post(reverse("issues:update", args=[issue.pk]), data)


class RaiseIssueTests(IssueTestCase):
    def test_raise_records_timeline_audit_and_tells_everyone_else(self):
        response = self.client.post(reverse("issues:create"), {
            "title": "Camera clocks out of sync", "description": "All cameras show different times.",
            "location": "Lobby", "category": "SECURITY", "priority": "HIGH",
        })

        issue = Issue.objects.get()
        self.assertRedirects(response, reverse("issues:detail", args=[issue.pk]))
        self.assertEqual((issue.strata, issue.raised_by, issue.status), (self.strata, self.council.user, Status.OPEN))
        self.assertEqual(list(issue.updates.values_list("kind", flat=True)), [IssueUpdate.Kind.CREATED])
        self.assertTrue(AuditLog.objects.filter(object_id=str(issue.pk), action=AuditLog.Action.CREATE).exists())
        self.assertEqual([m.to for m in mail.outbox], [[self.manager.user.email]])  # not the raiser

    def test_owner_must_be_a_member_of_this_building(self):
        outsider = make_membership(make_user(), make_strata()).user
        response = self.client.post(reverse("issues:create"), {
            "title": "Leak", "category": "MAINTENANCE", "priority": "NORMAL", "assigned_to": outsider.pk,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("assigned_to", response.context["form"].errors)
        self.assertFalse(Issue.objects.exists())

    def test_rejects_bad_input(self):
        response = self.client.post(reverse("issues:create"), {"title": "", "category": "BOGUS", "priority": "X"})
        self.assertEqual(set(response.context["form"].errors), {"title", "category", "priority"})

    def test_assigning_on_raise_emails_the_owner(self):
        self.client.post(reverse("issues:create"), {
            "title": "Leak", "category": "MAINTENANCE", "priority": "NORMAL", "assigned_to": self.manager.user.pk,
        })
        subjects = [m.subject for m in mail.outbox]
        self.assertIn("You now own: Leak", subjects)


class FromEmailTests(IssueTestCase):
    def email(self, strata=None, **summary):
        return InboundEmail.objects.create(
            strata=strata or self.strata, from_email="owner@example.com", subject="Fwd: locker",
            summary={"title": "Locker break-in", "summary": "Bike stolen.", "category": "Owner Request",
                     "urgency": "high", **summary}, status="READY",
        )

    def test_prefills_from_the_summary_and_links_the_email(self):
        email = self.email()
        response = self.client.get(reverse("issues:create"), {"from_email": email.pk})
        self.assertContains(response, 'value="Locker break-in"')

        self.client.post(reverse("issues:create"), {
            "from_email": email.pk, "title": "Locker break-in", "category": "SECURITY", "priority": "HIGH",
        })
        issue = Issue.objects.get()
        self.assertEqual(issue.source_email, email)
        self.assertContains(self.client.get(reverse("inbox:detail", args=[email.pk])), "Tracked as an issue")

    def test_ignores_another_buildings_email_and_bad_ids(self):
        theirs = self.email(strata=make_strata())
        for value in (theirs.pk, "not-a-uuid"):
            response = self.client.get(reverse("issues:create"), {"from_email": value})
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.context["source_email"])

    def test_turned_into_an_issue_means_handled_on_the_overview(self):
        email = self.email()
        self.assertIn("Urgent email: Locker break-in", [n.title for n in overview.needs_you(self.manager)])
        self.issue(source_email=email)
        self.assertNotIn("Urgent email: Locker break-in", [n.title for n in overview.needs_you(self.manager)])


class UpdateIssueTests(IssueTestCase):
    def test_assigning_acknowledges_and_emails_the_new_owner(self):
        issue = self.issue()
        self.post_update(issue, assigned_to=self.manager.user.pk)

        issue.refresh_from_db()
        self.assertEqual((issue.status, issue.assigned_to), (Status.ACKNOWLEDGED, self.manager.user))
        self.assertIsNotNone(issue.acknowledged_at)
        self.assertEqual(mail.outbox[-1].to, [self.manager.user.email])

    def test_closing_needs_an_outcome(self):
        issue = self.issue(status=Status.IN_PROGRESS)
        response = self.post_update(issue, status=Status.RESOLVED)
        self.assertEqual(response.status_code, 400)
        self.assertIn("outcome", response.context["form"].errors)

        self.post_update(issue, status=Status.RESOLVED, outcome="Locksmith replaced the strike plate.")
        issue.refresh_from_db()
        self.assertEqual((issue.status, issue.outcome), (Status.RESOLVED, "Locksmith replaced the strike plate."))
        self.assertIsNotNone(issue.resolved_at)
        self.assertIn("Outcome: Locksmith", issue.updates.get(kind=IssueUpdate.Kind.STATUS).body)

    def test_reopening_clears_the_resolved_date(self):
        issue = self.issue(status=Status.RESOLVED, resolved_at=timezone.now(), outcome="Fixed")
        self.post_update(issue, status=Status.IN_PROGRESS, comment="It's broken again.")
        issue.refresh_from_db()
        self.assertEqual(issue.status, Status.IN_PROGRESS)
        self.assertIsNone(issue.resolved_at)

    def test_comment_only_and_nothing_changed(self):
        issue = self.issue()
        self.assertEqual(self.post_update(issue).status_code, 400)  # nothing to update

        self.post_update(issue, comment="Locksmith booked for Tuesday.")
        self.assertEqual(issue.updates.last().body, "Locksmith booked for Tuesday.")
        self.assertTrue(AuditLog.objects.filter(object_id=str(issue.pk), action=AuditLog.Action.UPDATE).exists())

    def test_manager_can_update_too(self):
        issue = self.issue()
        self.client.force_login(self.manager.user)
        self.post_update(issue, status=Status.IN_PROGRESS, vendor="ABC Locksmith", due_date="2026-11-20")
        issue.refresh_from_db()
        self.assertEqual((issue.status, issue.vendor, issue.due_date),
                         (Status.IN_PROGRESS, "ABC Locksmith", datetime.date(2026, 11, 20)))

    def test_update_requires_post(self):
        issue = self.issue()
        self.assertEqual(self.client.get(reverse("issues:update", args=[issue.pk])).status_code, 405)


class UpdateEdgeTests(IssueTestCase):
    def test_closing_a_resolved_issue_keeps_its_outcome(self):
        issue = self.issue(status=Status.RESOLVED, outcome="Gate motor replaced.")
        self.post_update(issue, status="CLOSED")
        issue.refresh_from_db()
        self.assertEqual((issue.status, issue.outcome), (Status.CLOSED, "Gate motor replaced."))

    def test_a_former_members_issue_can_still_get_a_comment(self):
        former = make_membership(make_user(), self.strata, status=Membership.Status.INACTIVE).user
        issue = self.issue(assigned_to=former)
        self.post_update(issue, comment="Following up with the vendor.")
        self.assertTrue(issue.updates.filter(body="Following up with the vendor.").exists())


class IsolationAndListTests(IssueTestCase):
    def test_cannot_see_or_change_another_buildings_issue(self):
        theirs = self.issue(strata=make_strata(), title="Their issue")
        self.assertEqual(self.client.get(reverse("issues:detail", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.post_update(theirs, comment="hi").status_code, 404)
        self.assertNotContains(self.client.get(reverse("issues:list")), "Their issue")

    def test_tabs(self):
        self.issue(title="Mine open", assigned_to=self.council.user, status=Status.ACKNOWLEDGED)
        self.issue(title="Unowned open")
        self.issue(title="Done", status=Status.RESOLVED, resolved_at=timezone.now(), outcome="ok")

        def titles(show):
            return [i.title for i in self.client.get(reverse("issues:list"), {"show": show}).context["issues"]]

        self.assertEqual(sorted(titles("open")), ["Mine open", "Unowned open"])
        self.assertEqual(titles("mine"), ["Mine open"])
        self.assertEqual(titles("closed"), ["Done"])
        self.assertEqual(len(titles("bogus")), 2)  # falls back to open

    def test_requires_an_active_membership(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("issues:list")).status_code, 302)


class ConnectionsTests(IssueTestCase):
    def test_fix_by_dates_show_on_the_calendar(self):
        today = timezone.localdate()
        self.issue(title="Open late", due_date=today - datetime.timedelta(days=1))
        self.issue(title="Done late", due_date=today - datetime.timedelta(days=1), status=Status.RESOLVED)

        events = {e.title: e.status for e in feed.events_between(self.strata, today - datetime.timedelta(days=5), today)}
        self.assertEqual(events, {"Fix by · Open late": "overdue", "Fix by · Done late": "done"})

    def test_overview_by_role(self):
        self.issue(title="New one")
        self.issue(title="Given to Sara", assigned_to=self.council.user, status=Status.ACKNOWLEDGED)

        council = {n.title: n.on_you for n in overview.needs_you(self.council)}
        manager = {n.title: n.on_you for n in overview.needs_you(self.manager)}
        self.assertEqual(council, {"No response yet: New one": False, "Assigned to you: Given to Sara": True})
        self.assertEqual(manager, {"New issue: New one": True})

    def test_quiet_issues_are_flagged(self):
        issue = self.issue(status=Status.IN_PROGRESS, assigned_to=self.manager.user)
        Issue.objects.filter(pk=issue.pk).update(last_activity_at=timezone.now() - datetime.timedelta(days=20))
        self.assertTrue(any(n.title.startswith("Gone quiet") for n in overview.needs_you(self.council)))

    def test_enforcement_cases_are_bylaw_only(self):
        self.client.post(reverse("dockets:incident_create"), {
            "title": "Broken door", "incident_type": "DEFICIENCY", "description": "d",
        })
        self.assertEqual(Incident.objects.get().incident_type, Incident.Type.BYLAW)
