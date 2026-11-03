import io
import shutil
import tempfile

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from core.dev import DEMO_PLAN
from core.models import User
from stratas.models import Membership, StrataPlan

MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(DEBUG=True, MEDIA_ROOT=MEDIA_ROOT)
class InitDemoDataTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def test_seeds_a_presentable_demo_building_once(self):
        call_command("init_demo_data", stdout=io.StringIO())

        strata = StrataPlan.objects.get(plan_number=DEMO_PLAN)
        self.assertEqual(strata.memberships.active().council().count(), 7)
        self.assertEqual(strata.memberships.pending().count(), 1)
        self.assertEqual(
            set(strata.incidents.values_list("status", flat=True)),
            {"IN_REVIEW", "NOTICE_ISSUED", "VOTING_OPEN", "RESOLVED_FINED", "RESOLVED_DISMISSED"},
        )
        self.assertTrue(strata.documents.exists() and strata.document_questions.exists())
        self.assertTrue(strata.inbound_emails.exists() and strata.key_dates.exists())
        self.assertEqual(strata.issues.open().count(), 5)
        self.assertFalse(strata.incidents.filter(incident_type="DEFICIENCY").exists())  # those are issues now
        self.assertEqual(sorted(strata.meetings.values_list("status", flat=True)), ["APPROVED", "HELD", "PLANNED"])
        upcoming = strata.meetings.get(status="PLANNED")
        self.assertTrue(upcoming.items.filter(issue__isnull=False).exists())
        self.assertTrue(upcoming.items.filter(incident__isnull=False, in_camera=True).exists())
        self.assertEqual(
            Membership.objects.filter(user__email="manager@civicdesk.test", status="ACTIVE").count(), 3
        )
        self.assertFalse(User.objects.exclude(email__endswith=".test").exists())  # never real email

        with self.assertRaises(CommandError):
            call_command("init_demo_data", stdout=io.StringIO())

    @override_settings(DEBUG=False)
    def test_refuses_without_debug(self):
        with self.assertRaises(CommandError):
            call_command("init_demo_data")
