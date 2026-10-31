from django.test import TestCase

from core.models import AuditLog
from core.services import record_audit_log
from core.testing import make_strata, make_user
from dockets.models import Incident


class RecordAuditLogTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.incident = Incident.objects.create(strata=make_strata(), title="t", description="d")

    def test_explicit_action_is_always_logged_even_without_changes(self):
        log = record_audit_log(self.incident, self.user, action=AuditLog.Action.VOTE_CAST, custom_summary="Vote cast")
        self.assertIsNotNone(log)
        self.assertEqual((log.action, log.summary, log.actor), (AuditLog.Action.VOTE_CAST, "Vote cast", self.user))

    def test_create_right_after_objects_create_is_logged(self):
        log = record_audit_log(self.incident, self.user, action=AuditLog.Action.CREATE)
        self.assertEqual(log.summary, "Created Incident")

    def test_inferred_update_records_field_diff(self):
        self.incident.unit_number = "304"
        log = record_audit_log(self.incident, self.user)
        self.assertEqual(log.action, AuditLog.Action.UPDATE)
        self.assertEqual(log.changes["unit_number"], {"from": "", "to": "304"})

    def test_no_action_and_no_changes_writes_nothing(self):
        self.assertIsNone(record_audit_log(self.incident, self.user))
        self.assertFalse(AuditLog.objects.exists())

    def test_anonymous_actor_is_stored_without_user(self):
        log = record_audit_log(self.incident, None, action=AuditLog.Action.STATUS_CHANGE)
        self.assertIsNone(log.actor)
        self.assertEqual(log.actor_email, "")
