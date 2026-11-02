import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from core.testing import make_membership, make_strata, make_user
from dockets.models import Incident
from stratas.models import Membership
from . import feed
from .models import KeyDate

TODAY = datetime.date(2026, 11, 1)
MONTH_URL = reverse("schedule:month")


def freeze_today():
    return mock.patch("django.utils.timezone.localdate", return_value=TODAY)


class CalendarTestCase(TestCase):
    def setUp(self):
        self.strata = make_strata()
        self.user = make_user()
        make_membership(self.user, self.strata)
        self.client.force_login(self.user)

    def key_date(self, strata=None, **fields):
        fields = {"title": "Insurance renewal", "date": datetime.date(2026, 11, 26), **fields}
        return KeyDate.objects.create(strata=strata or self.strata, **fields)


class MonthViewTests(CalendarTestCase):
    def test_shows_this_months_events_with_a_count(self):
        self.key_date()
        self.key_date(title="AGM", date=datetime.date(2026, 11, 4))
        self.key_date(title="Next year", date=datetime.date(2027, 11, 4))

        with freeze_today():
            response = self.client.get(MONTH_URL)

        self.assertContains(response, "November 2026")
        self.assertContains(response, "2 dates")
        self.assertEqual([e.title for e in response.context["month_events"]], ["AGM", "Insurance renewal"])

    def test_month_selector_moves_between_months_and_years(self):
        with freeze_today():
            response = self.client.get(MONTH_URL, {"month": "2026-12"})

        self.assertContains(response, "December 2026")
        self.assertEqual(response.context["next_month"], datetime.date(2027, 1, 1))
        self.assertEqual(response.context["prev_month"], datetime.date(2026, 11, 1))

    def test_bad_month_input_falls_back_to_this_month(self):
        for bad in ("2026-13", "nope", "1899-01", "2026-1", "<script>"):
            with self.subTest(bad=bad), freeze_today():
                response = self.client.get(MONTH_URL, {"month": bad})
                self.assertEqual(response.context["month"], datetime.date(2026, 11, 1))

    def test_never_shows_another_buildings_dates(self):
        self.key_date(strata=make_strata(), title="Other building AGM")

        with freeze_today():
            response = self.client.get(MONTH_URL)

        self.assertNotContains(response, "Other building AGM")
        self.assertContains(response, "Nothing on the calendar")

    def test_manager_sees_the_active_buildings_calendar(self):
        manager = make_user()
        make_membership(manager, self.strata, role=Membership.Role.MANAGER)
        self.key_date()
        self.client.force_login(manager)

        with freeze_today():
            response = self.client.get(MONTH_URL)

        self.assertContains(response, "Insurance renewal")

    def test_requires_an_active_membership(self):
        pending = make_user()
        make_membership(pending, make_strata(), status=Membership.Status.PENDING)
        self.client.force_login(pending)
        self.assertEqual(self.client.get(MONTH_URL).status_code, 302)

        self.client.logout()
        self.assertEqual(self.client.get(MONTH_URL).status_code, 302)


class FeedTests(CalendarTestCase):
    def test_yearly_key_dates_repeat_from_their_first_year(self):
        self.key_date(title="Fiscal year starts", date=datetime.date(2025, 4, 1), repeats_yearly=True)

        with freeze_today():
            april_2027 = feed.events_between(self.strata, datetime.date(2027, 4, 1), datetime.date(2027, 4, 30))
            april_2024 = feed.events_between(self.strata, datetime.date(2024, 4, 1), datetime.date(2024, 4, 30))

        self.assertEqual([e.date for e in april_2027], [datetime.date(2027, 4, 1)])
        self.assertEqual(april_2024, [])

    def test_leap_day_repeats_on_feb_28(self):
        key_date = self.key_date(date=datetime.date(2028, 2, 29), repeats_yearly=True)
        self.assertEqual(
            key_date.occurrences(datetime.date(2029, 2, 1), datetime.date(2029, 2, 28)),
            [datetime.date(2029, 2, 28)],
        )

    def test_enforcement_deadlines_are_flagged(self):
        aware = lambda d: timezone.make_aware(datetime.datetime.combine(d, datetime.time(12)))
        Incident.objects.create(
            strata=self.strata, title="Overstay parking", description="d", unit_number="301",
            status=Incident.Status.NOTICE_ISSUED,
            notice_issued_at=aware(datetime.date(2026, 10, 15)),
            statutory_deadline=aware(datetime.date(2026, 10, 29)),
        )
        Incident.objects.create(
            strata=self.strata, title="Closed case", description="d",
            status=Incident.Status.RESOLVED_DISMISSED, statutory_deadline=aware(datetime.date(2026, 10, 20)),
        )

        with freeze_today():
            events = feed.events_between(self.strata, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))

        by_title = {e.title: e.status for e in events}
        self.assertEqual(by_title["Notice issued · Unit 301"], "done")
        self.assertEqual(by_title["Response due · Unit 301"], "overdue")
        self.assertEqual(by_title["Response due · Closed case"], "done")

    def test_due_soon_within_three_days(self):
        self.key_date(date=TODAY + datetime.timedelta(days=3))
        with freeze_today():
            [event] = feed.events_between(self.strata, TODAY, TODAY + datetime.timedelta(days=30))
        self.assertEqual(event.status, "soon")


class KeyDateViewTests(CalendarTestCase):
    def test_add_prefills_the_clicked_day(self):
        response = self.client.get(reverse("schedule:key_date_create"), {"date": "2026-11-26"})
        self.assertContains(response, 'value="2026-11-26"')

    def test_add_records_who_and_audits(self):
        response = self.client.post(reverse("schedule:key_date_create"), {
            "title": "AGM", "date": "2026-11-04", "category": "MEETING", "note": "",
        })

        key_date = KeyDate.objects.get()
        self.assertRedirects(response, f"{MONTH_URL}?month=2026-11")
        self.assertEqual((key_date.strata, key_date.created_by), (self.strata, self.user))
        self.assertTrue(AuditLog.objects.filter(object_id=str(key_date.pk), action=AuditLog.Action.CREATE).exists())

    def test_add_rejects_bad_input(self):
        response = self.client.post(reverse("schedule:key_date_create"), {
            "title": "", "date": "not-a-date", "category": "BOGUS",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(KeyDate.objects.exists())
        self.assertEqual(set(response.context["form"].errors), {"title", "date", "category"})

    def test_edit_and_remove_are_audited(self):
        key_date = self.key_date()
        url = reverse("schedule:key_date_update", args=[key_date.pk])

        self.client.post(url, {"title": "Insurance renewal", "date": "2026-11-27", "category": "INSURANCE"})
        key_date.refresh_from_db()
        self.assertEqual(key_date.date, datetime.date(2026, 11, 27))

        self.client.post(reverse("schedule:key_date_delete", args=[key_date.pk]))
        self.assertFalse(KeyDate.objects.exists())
        actions = set(AuditLog.objects.filter(object_id=str(key_date.pk)).values_list("action", flat=True))
        self.assertEqual(actions, {AuditLog.Action.UPDATE, AuditLog.Action.DELETE})

    def test_remove_requires_post(self):
        key_date = self.key_date()
        response = self.client.get(reverse("schedule:key_date_delete", args=[key_date.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(KeyDate.objects.exists())

    def test_cannot_touch_another_buildings_key_date(self):
        theirs = self.key_date(strata=make_strata())

        self.assertEqual(self.client.get(reverse("schedule:key_date_update", args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("schedule:key_date_delete", args=[theirs.pk])).status_code, 404)
        self.assertTrue(KeyDate.objects.filter(pk=theirs.pk).exists())


class OverdueTests(CalendarTestCase):
    def test_past_key_dates_are_past_not_overdue(self):
        self.key_date(date=TODAY - datetime.timedelta(days=1))
        with freeze_today():
            [event] = feed.events_between(self.strata, TODAY.replace(day=1) - datetime.timedelta(days=5), TODAY)
        self.assertEqual(event.status, "past")

    def test_current_month_lists_what_is_still_overdue_from_earlier(self):
        deadline = timezone.make_aware(datetime.datetime(2026, 10, 24, 12))
        Incident.objects.create(
            strata=self.strata, title="Garbage dumping", description="d", unit_number="112",
            status=Incident.Status.NOTICE_ISSUED, statutory_deadline=deadline,
        )

        with freeze_today():
            this_month = self.client.get(MONTH_URL)
            later = self.client.get(MONTH_URL, {"month": "2027-01"})

        self.assertEqual([e.title for e in this_month.context["still_overdue"]], ["Response due · Unit 112"])
        self.assertContains(this_month, "Still overdue from earlier")
        self.assertEqual(later.context["still_overdue"], [])


class ReviewFollowUpTests(CalendarTestCase):
    def incident(self, status, deadline, **fields):
        return Incident.objects.create(
            strata=self.strata, title="Overstay", description="d", unit_number="301",
            status=status, statutory_deadline=deadline, **fields,
        )

    def test_owner_who_replied_is_not_shown_overdue(self):
        self.incident(Incident.Status.VOTING_OPEN, timezone.make_aware(datetime.datetime(2026, 10, 20, 12)))

        with freeze_today():
            [event] = feed.events_between(self.strata, datetime.date(2026, 10, 1), datetime.date(2026, 10, 31))
            overdue = feed.still_overdue(self.strata, TODAY)

        self.assertEqual(event.status, "done")
        self.assertEqual(overdue, [])

    def test_still_overdue_has_no_lookback_limit(self):
        self.incident(Incident.Status.NOTICE_ISSUED, timezone.make_aware(datetime.datetime(2024, 1, 10, 12)))
        with freeze_today():
            self.assertEqual(len(feed.still_overdue(self.strata, TODAY)), 1)

    def test_late_evening_pacific_deadline_lands_on_the_pacific_day(self):
        # 23:30 Pacific on Oct 30 is 06:30 UTC on Oct 31.
        self.incident(Incident.Status.NOTICE_ISSUED, timezone.make_aware(datetime.datetime(2026, 10, 30, 23, 30)))

        with freeze_today():
            oct_30 = feed.events_between(self.strata, datetime.date(2026, 10, 30), datetime.date(2026, 10, 30))
            oct_31 = feed.events_between(self.strata, datetime.date(2026, 10, 31), datetime.date(2026, 10, 31))

        self.assertEqual([e.date for e in oct_30], [datetime.date(2026, 10, 30)])
        self.assertEqual(oct_31, [])

    def test_yearly_date_shows_on_the_previous_years_spill_days(self):
        self.key_date(title="Year-end close", date=datetime.date(2025, 12, 30), repeats_yearly=True)

        with freeze_today():
            response = self.client.get(MONTH_URL, {"month": "2027-01"})

        first_week = response.context["weeks"][0]
        self.assertEqual(first_week[0][0], datetime.date(2026, 12, 27))
        days_with_events = [day for day, events in first_week if events]
        self.assertEqual(days_with_events, [datetime.date(2026, 12, 30)])

    def test_manager_can_edit_and_remove_key_dates(self):
        manager = make_user()
        make_membership(manager, self.strata, role=Membership.Role.MANAGER)
        self.client.force_login(manager)
        key_date = self.key_date()

        self.client.post(reverse("schedule:key_date_update", args=[key_date.pk]),
                         {"title": "Insurance renewal", "date": "2026-11-28", "category": "INSURANCE"})
        key_date.refresh_from_db()
        self.assertEqual(key_date.date, datetime.date(2026, 11, 28))

        self.client.post(reverse("schedule:key_date_delete", args=[key_date.pk]))
        self.assertFalse(KeyDate.objects.exists())

    def test_cannot_edit_another_buildings_key_date_by_post(self):
        theirs = self.key_date(strata=make_strata())
        response = self.client.post(reverse("schedule:key_date_update", args=[theirs.pk]),
                                    {"title": "Hijacked", "date": "2026-11-28", "category": "OTHER"})
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.title, "Insurance renewal")

    def test_edit_audit_keeps_the_old_values_and_skips_no_op_saves(self):
        key_date = self.key_date()
        url = reverse("schedule:key_date_update", args=[key_date.pk])
        same = {"title": "Insurance renewal", "date": "2026-11-26", "category": "OTHER"}

        self.client.post(url, same)
        self.assertFalse(AuditLog.objects.filter(action=AuditLog.Action.UPDATE).exists())

        self.client.post(url, {**same, "date": "2026-11-30"})
        log = AuditLog.objects.get(action=AuditLog.Action.UPDATE)
        self.assertEqual(log.changes["date"], {"from": "2026-11-26", "to": "2026-11-30"})

    def test_invalid_clicked_day_is_ignored(self):
        response = self.client.get(reverse("schedule:key_date_create"), {"date": "<b>soon</b>"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "&lt;b&gt;soon")

    def test_failed_edit_keeps_the_saved_title_in_the_header(self):
        key_date = self.key_date()
        response = self.client.post(reverse("schedule:key_date_update", args=[key_date.pk]),
                                    {"title": "Typo title", "date": "bad", "category": "OTHER"})
        self.assertContains(response, "<title>Edit Insurance renewal</title>", html=False)


class MonthCardTests(CalendarTestCase):
    def test_shows_previous_current_and_next_month_highlights(self):
        self.key_date(title="Year-end", date=datetime.date(2026, 12, 31))
        self.key_date(title="Fiscal planning", date=datetime.date(2027, 1, 15))
        self.key_date(title="Budget", date=datetime.date(2027, 2, 1))
        self.key_date(title="Out of range", date=datetime.date(2027, 3, 1))

        with freeze_today():
            response = self.client.get(MONTH_URL, {"month": "2027-01"})

        months = response.context["months"]
        self.assertEqual([m["first"] for m in months],
                         [datetime.date(2026, 12, 1), datetime.date(2027, 1, 1), datetime.date(2027, 2, 1)])
        self.assertEqual([[e.title for e in m["events"]] for m in months], [["Year-end"], ["Fiscal planning"], ["Budget"]])
        self.assertEqual([m["is_current"] for m in months], [False, True, False])
        self.assertContains(response, 'href="?month=2026-12"')
        self.assertNotContains(response, "Out of range")

    def test_card_highlights_put_overdue_first(self):
        for day in (2, 3, 4):
            self.key_date(title=f"Past {day}", date=datetime.date(2026, 10, day))
        Incident.objects.create(
            strata=self.strata, title="Silent owner", description="d", unit_number="410",
            status=Incident.Status.NOTICE_ISSUED,
            statutory_deadline=timezone.make_aware(datetime.datetime(2026, 10, 27, 12)),
        )

        with freeze_today():
            response = self.client.get(MONTH_URL)

        october = response.context["months"][0]
        self.assertEqual(october["highlights"][0].title, "Response due · Unit 410")
        self.assertEqual(len(october["highlights"]), 3)
