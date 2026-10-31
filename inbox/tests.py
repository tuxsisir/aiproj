from unittest import mock

from anymail.inbound import AnymailInboundMessage
from anymail.signals import AnymailInboundEvent, inbound
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from core.testing import make_membership, make_strata, make_user
from stratas.models import Membership
from . import ai, services
from .models import InboundEmail, Inbox

SUMMARY = {
    "title": "Parkade leak near stall 42",
    "summary": "Water is dripping onto cars. Plumber booked Tuesday.",
    "category": "Maintenance & Repairs",
    "urgency": "high",
    "people": [{"name": "Dave", "role": "Plumber", "email": ""}],
    "action_items": [{"task": "Confirm plumber access", "owner": "Manager", "due": "Tuesday"}],
    "open_questions": ["Is this covered by insurance?"],
    "suggested_next_step": "Notify affected owners.",
}


@override_settings(INBOUND_EMAIL_DOMAIN="inbox.example.com", ANTHROPIC_API_KEY="test-key")
class InboxTestCase(TestCase):
    def setUp(self):
        self.strata = make_strata("EPS42")
        self.member = make_membership(make_user("Treasurer@Example.com"), self.strata)
        self.inbox = services.get_or_create_inbox(self.strata)

    def forward(self, sender="treasurer@example.com", to=None, event_id="evt_1", **extra):
        message = AnymailInboundMessage.construct(
            from_email=f"Sam <{sender}>", to=to or self.inbox.address, subject="Fwd: Leak in parkade",
            text="---------- Forwarded message ---------\nWater dripping on stall 42.", **extra,
        )
        event = AnymailInboundEvent(event_type="inbound", event_id=event_id, message=message, esp_event={"data": {}})
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            inbound.send(sender=None, event=event, esp_name="Resend")
        return callbacks


class ReceiveTests(InboxTestCase):
    def test_address_is_unguessable_and_on_inbound_domain(self):
        self.assertRegex(self.inbox.address, r"^eps42-[0-9a-f]{6}@inbox\.example\.com$")
        self.assertEqual(services.get_or_create_inbox(self.strata), self.inbox)

    def test_member_forward_is_stored_and_summary_queued(self):
        callbacks = self.forward()
        email = InboundEmail.objects.get()
        self.assertEqual((email.strata, email.forwarded_by), (self.strata, self.member.user))
        self.assertEqual(email.subject, "Fwd: Leak in parkade")
        self.assertIn("stall 42", email.body_text)
        self.assertEqual(len(callbacks), 1)

    def test_inbox_matched_from_cc_too(self):
        self.forward(to="someone@else.com", cc=self.inbox.address.upper())
        self.assertTrue(InboundEmail.objects.exists())

    def test_non_member_and_inactive_member_are_ignored(self):
        self.forward(sender="stranger@example.com", event_id="e1")
        inactive = make_membership(make_user("old@example.com"), self.strata, status=Membership.Status.INACTIVE)
        self.forward(sender=inactive.user.email, event_id="e2")
        self.assertFalse(InboundEmail.objects.exists())

    def test_member_of_another_building_is_ignored(self):
        outsider = make_membership(make_user("outsider@example.com"), make_strata())
        self.forward(sender=outsider.user.email)
        self.assertFalse(InboundEmail.objects.exists())

    def test_unknown_inbox_is_ignored(self):
        self.forward(to="nobody-123456@inbox.example.com")
        self.assertFalse(InboundEmail.objects.exists())

    def test_duplicate_webhook_delivery_is_ignored(self):
        self.forward(event_id="same")
        self.forward(event_id="same")
        self.assertEqual(InboundEmail.objects.count(), 1)

    def test_attachment_metadata_is_kept(self):
        attachment = AnymailInboundMessage.construct_attachment("application/pdf", b"%PDF-1.4", filename="quote.pdf")
        self.forward(attachments=[attachment])
        self.assertEqual(InboundEmail.objects.get().attachments, [{"filename": "quote.pdf", "content_type": "application/pdf", "size": 8}])


class SummarizeTests(InboxTestCase):
    def make_email(self, **extra):
        return InboundEmail.objects.create(
            strata=self.strata, forwarded_by=self.member.user, from_email="treasurer@example.com",
            subject="Fwd: Leak", body_text="Water dripping.", **extra,
        )

    @mock.patch.object(ai, "summarize_email", return_value=SUMMARY)
    def test_summary_stored_and_emailed_back_to_forwarder(self, summarize_email):
        email = services.summarize(self.make_email())
        self.assertEqual((email.status, email.summary), (InboundEmail.Status.READY, SUMMARY))
        self.assertEqual(mail.outbox[-1].to, [self.member.user.email])
        self.assertIn("Parkade leak near stall 42", mail.outbox[-1].subject)
        self.assertIn("Confirm plumber access", mail.outbox[-1].body)

    @mock.patch.object(ai, "summarize_email", side_effect=ai.AIError("Service unavailable"))
    def test_failure_is_recorded(self, summarize_email):
        email = services.summarize(self.make_email())
        self.assertEqual((email.status, email.error), (InboundEmail.Status.FAILED, "Service unavailable"))

    @override_settings(ANTHROPIC_API_KEY="")
    def test_without_ai_key_email_is_kept_but_marked_failed(self):
        self.forward()
        self.assertEqual(InboundEmail.objects.get().status, InboundEmail.Status.FAILED)


class InboxViewTests(InboxTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.member.user)

    def test_home_shows_forwarding_address(self):
        self.assertContains(self.client.get(reverse("inbox:home")), self.inbox.address)

    def test_detail_shows_summary(self):
        email = InboundEmail.objects.create(
            strata=self.strata, from_email="treasurer@example.com", summary=SUMMARY, status=InboundEmail.Status.READY,
        )
        response = self.client.get(reverse("inbox:detail", args=[email.pk]))
        self.assertContains(response, "Parkade leak near stall 42")
        self.assertContains(response, "Notify affected owners.")

    def test_pending_summary_shows_ai_animation_and_polls(self):
        email = InboundEmail.objects.create(strata=self.strata, from_email="treasurer@example.com")
        response = self.client.get(reverse("inbox:summary", args=[email.pk]))
        self.assertContains(response, 'hx-trigger="every 3s"')
        self.assertContains(response, "ai-shimmer")

    def test_other_buildings_emails_are_hidden(self):
        email = InboundEmail.objects.create(strata=make_strata(), from_email="x@example.com", subject="Private")
        for name in ("detail", "summary"):
            self.assertEqual(self.client.get(reverse(f"inbox:{name}", args=[email.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("inbox:home")), "Private")

    def test_retry_requeues(self):
        email = InboundEmail.objects.create(strata=self.strata, from_email="x@example.com", status=InboundEmail.Status.FAILED)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(reverse("inbox:retry", args=[email.pk]))
        email.refresh_from_db()
        self.assertEqual((email.status, len(callbacks)), (InboundEmail.Status.PENDING, 1))
