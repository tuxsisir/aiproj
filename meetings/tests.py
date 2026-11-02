import datetime

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import overview
from core.models import AuditLog
from core.testing import make_membership, make_strata, make_user
from dockets.models import Incident, IncidentEvent
from issues.models import Issue, IssueUpdate
from schedule import feed
from stratas.models import Membership
from . import services
from .models import AgendaItem, Meeting

Status = Meeting.Status


def local(days, hour=19):
    day = timezone.localdate() + datetime.timedelta(days=days)
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))


class MeetingTestCase(TestCase):
    def setUp(self):
        self.strata = make_strata()
        self.council = make_membership(make_user(first_name="Sara"), self.strata)
        self.other_council = make_membership(make_user(first_name="Omar"), self.strata)
        self.manager = make_membership(make_user(first_name="Mike"), self.strata, role=Membership.Role.MANAGER)
        self.client.force_login(self.council.user)
        self.issue = Issue.objects.create(strata=self.strata, title="Gate sticks open", raised_by=self.council.user)
        self.case = Incident.objects.create(strata=self.strata, title="Loud music", unit_number="1204",
                                            description="After 11 pm.")

    def meeting(self, days=7, status=Status.PLANNED, strata=None, **fields):
        meeting = Meeting.objects.create(strata=strata or self.strata, starts_at=local(days), status=status,
                                         created_by=self.manager.user, **fields)
        services.build_agenda(meeting, [self.issue], [self.case] if strata is None else [])
        return meeting

    def items(self, meeting):
        return list(meeting.items.values_list("title", flat=True))

    def record(self, meeting, action="save", attendees=(), guests="", **by_title):
        """POST the minutes formset; by_title maps an item title to (minutes, decision)."""
        items = list(meeting.items.all())
        data = {"form-TOTAL_FORMS": len(items), "form-INITIAL_FORMS": len(items), "action": action,
                "attendees": [u.pk for u in attendees], "guests": guests}
        for i, item in enumerate(items):
            minutes, decision = by_title.get(item.title, ("", ""))
            data.update({f"form-{i}-id": item.pk, f"form-{i}-minutes": minutes, f"form-{i}-decision": decision})
        return self.client.post(reverse("meetings:record", args=[meeting.pk]), data)


class PlanMeetingTests(MeetingTestCase):
    def test_form_offers_open_items_of_this_building_only(self):
        Issue.objects.create(strata=self.strata, title="Fixed already", status=Issue.Status.RESOLVED)
        Issue.objects.create(strata=make_strata(), title="Someone else's leak")
        response = self.client.get(reverse("meetings:create"))
        form = response.context["form"]
        self.assertEqual([i.title for i in form.fields["issues"].queryset], ["Gate sticks open"])
        self.assertEqual([c.title for c in form.fields["cases"].queryset], ["Loud music"])
        self.assertContains(response, "Gate sticks open")

    def test_plan_builds_the_agenda_and_sends_it_to_everyone_else(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("meetings:create"), {
                "kind": "COUNCIL", "starts_at": "2030-03-04T19:00", "location": "Amenity room",
                "issues": [self.issue.pk], "cases": [self.case.pk],
            })

        meeting = Meeting.objects.get()
        self.assertRedirects(response, reverse("meetings:detail", args=[meeting.pk]))
        self.assertEqual(timezone.localtime(meeting.starts_at).hour, 19)  # entered in local time
        self.assertEqual(self.items(meeting), [
            "Call to order", "Approval of the agenda", "Financial report", "Manager's report",
            "Issue: Gate sticks open", "Enforcement: Unit 1204, Loud music", "New business", "Adjournment",
        ])  # first meeting: no previous minutes to approve
        case_item = meeting.items.get(incident=self.case)
        self.assertTrue(case_item.in_camera)
        self.assertFalse(meeting.items.get(issue=self.issue).in_camera)
        self.assertTrue(AuditLog.objects.filter(object_id=str(meeting.pk), action=AuditLog.Action.CREATE).exists())
        self.assertEqual(sorted(m.to[0] for m in mail.outbox),
                         sorted([self.other_council.user.email, self.manager.user.email]))

    def test_unticked_items_stay_off_and_previous_minutes_are_added_once_there_are_some(self):
        self.meeting(days=-30, status=Status.APPROVED)
        self.client.post(reverse("meetings:create"), {"kind": "COUNCIL", "starts_at": "2030-03-04T19:00"})
        meeting = Meeting.objects.get(status=Status.PLANNED)
        self.assertIn("Approval of the previous minutes", self.items(meeting))
        self.assertFalse(meeting.items.filter(issue__isnull=False).exists())

    def test_rejects_another_buildings_issue(self):
        foreign = Issue.objects.create(strata=make_strata(), title="Not ours")
        response = self.client.post(reverse("meetings:create"), {
            "kind": "COUNCIL", "starts_at": "2030-03-04T19:00", "issues": [foreign.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("issues", response.context["form"].errors)
        self.assertFalse(Meeting.objects.exists())


class AgendaTests(MeetingTestCase):
    def test_added_item_goes_before_new_business(self):
        meeting = self.meeting()
        self.client.post(reverse("meetings:item_add", args=[meeting.pk]),
                         {"title": "Gutter quotes", "details": "", "in_camera": ""})
        self.assertEqual(self.items(meeting)[-3:], ["Gutter quotes", "New business", "Adjournment"])

    def test_move_and_remove(self):
        meeting = self.meeting()
        second = meeting.items.get(title="Approval of the agenda")
        self.client.post(reverse("meetings:item_move", args=[second.pk]), {"direction": "up"})
        self.assertEqual(self.items(meeting)[:2], ["Approval of the agenda", "Call to order"])
        self.client.post(reverse("meetings:item_remove", args=[second.pk]))
        self.assertNotIn("Approval of the agenda", self.items(meeting))

    def test_agenda_is_locked_once_held(self):
        meeting = self.meeting(days=-1, status=Status.HELD)
        before = self.items(meeting)
        self.client.post(reverse("meetings:item_add", args=[meeting.pk]), {"title": "Late item"})
        self.client.post(reverse("meetings:item_remove", args=[meeting.items.first().pk]))
        self.assertEqual(self.items(meeting), before)

    def test_other_buildings_meetings_and_items_are_not_found(self):
        foreign = self.meeting(strata=make_strata())
        item = foreign.items.first()
        self.assertEqual(self.client.get(reverse("meetings:detail", args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("meetings:item_remove", args=[item.pk])).status_code, 404)
        self.assertTrue(AgendaItem.objects.filter(pk=item.pk).exists())


class MinutesTests(MeetingTestCase):
    def test_save_minutes_keeps_the_meeting_planned(self):
        meeting = self.meeting(days=0)
        self.record(meeting, **{"Financial report": ("On budget.", "Report accepted.")})
        item = meeting.items.get(title="Financial report")
        self.assertEqual((item.minutes, item.decision), ("On budget.", "Report accepted."))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.PLANNED)

    def test_marking_held_needs_attendance(self):
        meeting = self.meeting(days=0)
        response = self.record(meeting, action="held")
        self.assertEqual(response.status_code, 400)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.PLANNED)

    def test_held_asks_council_to_approve_but_posts_nothing_to_timelines_yet(self):
        meeting = self.meeting(days=0)
        with self.captureOnCommitCallbacks(execute=True):
            self.record(meeting, action="held", attendees=[self.council.user, self.manager.user],
                        guests="Owner of 1204",
                        **{"Issue: Gate sticks open": ("", "Approve the gate repair up to $900."),
                           "Enforcement: Unit 1204, Loud music": ("Hearing held.", "Fine $200.")})

        meeting.refresh_from_db()
        self.assertEqual((meeting.status, meeting.guests), (Status.HELD, "Owner of 1204"))
        self.assertEqual(set(meeting.attendees.all()), {self.council.user, self.manager.user})
        self.assertFalse(self.issue.updates.filter(kind=IssueUpdate.Kind.COMMENT).exists())  # draft minutes
        self.assertFalse(self.case.events.filter(event_type=IncidentEvent.EventType.NOTE).exists())
        self.assertEqual([m.to for m in mail.outbox], [[self.other_council.user.email]])  # council, not the recorder

    def test_approval_posts_the_corrected_decisions_to_linked_items(self):
        meeting = self.meeting(days=0)
        self.record(meeting, action="held", attendees=[self.council.user],
                    **{"Issue: Gate sticks open": ("", "Hire A."),
                       "Enforcement: Unit 1204, Loud music": ("Hearing held.", "Fine $200.")})
        self.record(meeting, **{"Issue: Gate sticks open": ("", "Hire B (corrected)."),
                                "Enforcement: Unit 1204, Loud music": ("Hearing held.", "Fine $200.")})

        self.client.post(reverse("meetings:approve", args=[meeting.pk]))
        self.client.post(reverse("meetings:approve", args=[meeting.pk]))  # double submit: posted once

        update = self.issue.updates.get(kind=IssueUpdate.Kind.COMMENT)
        self.assertIn("(minutes approved): Hire B (corrected).", update.body)
        note = self.case.events.get(event_type=IncidentEvent.EventType.NOTE)
        self.assertIn("(in camera, minutes approved): Fine $200.", note.description)

    def test_marking_held_twice_does_nothing_the_second_time(self):
        meeting = self.meeting(days=0)
        self.assertIsNotNone(services.mark_held(meeting, self.council.user, attendees=[self.council.user]))
        self.assertIsNone(services.mark_held(meeting, self.council.user, attendees=[self.council.user]))
        self.assertEqual(AuditLog.objects.filter(summary="Meeting held; minutes in draft").count(), 1)

    def test_minutes_changes_are_audited(self):
        meeting = self.meeting(days=0)
        self.record(meeting, **{"Call to order": ("7:02 pm", "")})
        self.record(meeting, **{"Call to order": ("7:02 pm", "")})  # unchanged: no second entry
        self.assertEqual(AuditLog.objects.filter(summary="Minutes changed: Call to order").count(), 1)

    def test_minutes_for_another_buildings_item_are_rejected(self):
        meeting = self.meeting(days=0)
        other_item = self.meeting(strata=make_strata()).items.first()
        items = list(meeting.items.all())
        data = {"form-TOTAL_FORMS": len(items), "form-INITIAL_FORMS": len(items), "action": "save"}
        for i, item in enumerate(items):
            data.update({f"form-{i}-id": item.pk, f"form-{i}-minutes": "", f"form-{i}-decision": ""})
        data["form-0-id"], data["form-0-minutes"] = other_item.pk, "Hijacked"
        response = self.client.post(reverse("meetings:record", args=[meeting.pk]), data)
        self.assertRedirects(response, reverse("meetings:detail", args=[meeting.pk]))  # refused, nothing saved
        self.assertEqual(AgendaItem.objects.filter(minutes="Hijacked").count(), 0)
        other_item.refresh_from_db()
        self.assertEqual(other_item.minutes, "")

    def test_stale_or_padded_minutes_form_is_refused_without_saving(self):
        meeting = self.meeting(days=0)
        items = list(meeting.items.all())
        data = {"form-TOTAL_FORMS": len(items) + 1, "form-INITIAL_FORMS": len(items), "action": "save"}
        for i, item in enumerate(items):
            data.update({f"form-{i}-id": item.pk, f"form-{i}-minutes": "Saved?", f"form-{i}-decision": ""})
        data.update({f"form-{len(items)}-minutes": "Extra row", f"form-{len(items)}-decision": ""})
        response = self.client.post(reverse("meetings:record", args=[meeting.pk]), data)
        self.assertRedirects(response, reverse("meetings:detail", args=[meeting.pk]))
        self.assertFalse(meeting.items.filter(minutes="Saved?").exists())
        self.assertEqual(meeting.items.count(), len(items))

    def test_attendees_must_be_members_of_this_building(self):
        meeting = self.meeting(days=0)
        outsider = make_membership(make_user(), make_strata()).user
        self.assertEqual(self.record(meeting, action="held", attendees=[outsider]).status_code, 400)

    def test_only_council_approves_and_approved_minutes_are_locked(self):
        meeting = self.meeting(days=-1, status=Status.HELD)
        self.client.force_login(self.manager.user)
        self.assertEqual(self.client.post(reverse("meetings:approve", args=[meeting.pk])).status_code, 403)

        self.client.force_login(self.council.user)
        self.client.post(reverse("meetings:approve", args=[meeting.pk]))
        meeting.refresh_from_db()
        self.assertEqual((meeting.status, meeting.approved_by), (Status.APPROVED, self.council.user))

        self.record(meeting, **{"Call to order": ("Changed afterwards", "")})
        self.assertEqual(meeting.items.get(title="Call to order").minutes, "")

    def test_approve_needs_held_minutes(self):
        meeting = self.meeting()
        self.client.post(reverse("meetings:approve", args=[meeting.pk]))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.PLANNED)

    def test_cancel(self):
        meeting = self.meeting()
        self.assertRedirects(self.client.post(reverse("meetings:cancel", args=[meeting.pk])),
                             reverse("meetings:list"))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, Status.CANCELLED)

    def test_owners_copy_leaves_out_in_camera_details(self):
        meeting = self.meeting(days=-1, status=Status.HELD, guests="Owner of 1204")
        meeting.items.filter(incident=self.case).update(minutes="Owner says it was a party.", decision="Fine $200.")
        url = reverse("meetings:minutes", args=[meeting.pk])

        council_copy = self.client.get(url)
        self.assertContains(council_copy, "Fine $200.")
        self.assertContains(council_copy, "Draft: not yet approved")

        owners_copy = self.client.get(url, {"copy": "owners"})
        self.assertContains(owners_copy, "In-camera matter")
        for private in ["Loud music", "Fine $200.", "party", "Owner of 1204"]:
            self.assertNotContains(owners_copy, private)


class PagesTests(MeetingTestCase):
    def test_list_groups_meetings(self):
        self.meeting(days=7)
        self.meeting(days=-2)  # not recorded
        self.meeting(days=-9, status=Status.HELD)
        self.meeting(days=-40, status=Status.APPROVED)
        response = self.client.get(reverse("meetings:list"))
        self.assertEqual([len(response.context[k]) for k in ("upcoming", "unrecorded", "awaiting", "past")],
                         [1, 1, 1, 1])
        self.assertContains(response, "Minutes waiting for council approval")

    def test_detail_opens_on_agenda_before_and_minutes_after(self):
        before = self.client.get(reverse("meetings:detail", args=[self.meeting(days=3).pk]))
        self.assertEqual(before.context["tab"], "agenda")
        self.assertContains(before, "Add to agenda")
        after = self.client.get(reverse("meetings:detail", args=[self.meeting(days=-1).pk]))
        self.assertEqual(after.context["tab"], "minutes")
        self.assertContains(after, "Save and mark as held")


class CalendarAndOverviewTests(MeetingTestCase):
    def test_calendar_shows_meetings_on_their_local_day(self):
        late = Meeting.objects.create(strata=self.strata, starts_at=local(2, hour=23))  # next day in UTC
        Meeting.objects.create(strata=self.strata, starts_at=local(3), status=Status.CANCELLED)
        missed = Meeting.objects.create(strata=self.strata, starts_at=local(-2))
        today = timezone.localdate()
        events = {e.date: e for e in feed.events_between(self.strata, today - datetime.timedelta(days=5),
                                                         today + datetime.timedelta(days=5))
                  if e.pillar == "Meeting"}
        self.assertEqual(set(events), {timezone.localtime(late.starts_at).date(),
                                       timezone.localtime(missed.starts_at).date()})
        self.assertEqual(events[timezone.localtime(late.starts_at).date()].detail, "11:00 pm")
        self.assertEqual(events[timezone.localtime(missed.starts_at).date()].status, "overdue")

    def test_needs_you_by_role(self):
        self.meeting(days=-9, status=Status.HELD)
        self.meeting(days=-2)
        council = {n.title.split(":")[0]: n for n in overview.needs_you(self.council) if n.pillar == "Meetings"}
        manager = {n.title.split(":")[0]: n for n in overview.needs_you(self.manager) if n.pillar == "Meetings"}
        self.assertTrue(council["Approve the minutes"].on_you)
        self.assertFalse(council["Record the minutes"].on_you)  # the manager planned it
        self.assertTrue(manager["Record the minutes"].on_you)
        self.assertFalse(manager["Minutes waiting for council approval"].on_you)
