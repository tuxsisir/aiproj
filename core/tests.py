import re

from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from core import emails
from core.models import AuditLog
from core.services import record_audit_log
from core.testing import make_membership, make_strata, make_user
from dockets.models import Incident
from stratas.models import Membership
from core.email_previews import sample_context


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



@override_settings(SITE_URL="https://app.example.com")
class EmailHelperTests(TestCase):
    def setUp(self):
        self.user = make_user("member@example.com", first_name="Sam")
        self.strata = make_strata()
        self.membership = make_membership(self.user, self.strata)
        self.incident = Incident.objects.create(strata=self.strata, title="Noise", description="Loud", unit_number="304")

    def test_every_registered_email_renders_and_sends(self):
        context = sample_context()
        for key in emails.EMAILS:
            with self.subTest(key=key):
                self.assertTrue(emails.send(key, ["to@example.com"], context))
        self.assertEqual(len(mail.outbox), len(emails.EMAILS))

    def test_each_recipient_gets_a_private_copy_with_text_and_html(self):
        emails.send("membership_approved", ["a@example.com", "b@example.com", "a@example.com", ""], {"membership": self.membership})
        self.assertEqual([m.to for m in mail.outbox], [["a@example.com"], ["b@example.com"]])
        message = mail.outbox[0]
        self.assertEqual(message.subject, f"You're approved for {self.strata.plan_number} on CivicDesk")
        self.assertIn("https://app.example.com/dashboard/", message.body)
        self.assertEqual(message.alternatives[0][1], "text/html")
        self.assertEqual(message.tags, ["membership"])

    def test_no_recipients_sends_nothing(self):
        self.assertFalse(emails.send("welcome", [], {"user": self.user}))
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_BACKEND="core.tests.FailingBackend")
    def test_failures_are_swallowed_unless_asked(self):
        self.assertFalse(emails.send("welcome", ["x@example.com"], {"user": self.user}))
        with self.assertRaises(ConnectionError):
            emails.send("welcome", ["x@example.com"], {"user": self.user}, fail_silently=False)


class FailingBackend:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise ConnectionError("provider down")


class AccountEmailTests(TestCase):
    def test_signup_sends_welcome_email(self):
        self.client.post(reverse("account_signup"), {
            "first_name": "Sam", "last_name": "G", "email": "new@example.com", "password1": "a-Strong-pass-937",
        })
        self.assertEqual(mail.outbox[-1].subject, "Welcome to CivicDesk")
        self.assertEqual(mail.outbox[-1].to, ["new@example.com"])

    def test_password_reset_goes_through_helper(self):
        make_user("reset@example.com")
        self.client.post(reverse("account_reset_password"), {"email": "reset@example.com"})
        self.assertEqual(mail.outbox[-1].subject, "Reset your CivicDesk password")
        self.assertIn("/accounts/password/reset/key/", mail.outbox[-1].body)


class EmailPreviewTests(TestCase):
    def setUp(self):
        self.client.force_login(make_user("admin@example.com", is_staff=True, is_superuser=True))

    def test_list_shows_every_email(self):
        response = self.client.get(reverse("email_preview_list"))
        for key in emails.EMAILS:
            self.assertContains(response, reverse("email_preview", args=[key]))

    def test_preview_renders_html_and_text(self):
        self.assertContains(self.client.get(reverse("email_preview", args=["inbound_summarized"])), "Summary: Ceiling leak")
        html = self.client.get(reverse("email_preview_body", args=["inbound_summarized", "html"]))
        self.assertContains(html, "Approve emergency plumber call-out")
        self.assertEqual(html["X-Frame-Options"], "SAMEORIGIN")
        text = self.client.get(reverse("email_preview_body", args=["inbound_summarized", "text"]))
        self.assertEqual(text["Content-Type"], "text/plain; charset=utf-8")
        self.assertNotIn("<p", text.content.decode())

    def test_unknown_email_is_404(self):
        self.assertEqual(self.client.get(reverse("email_preview", args=["nope"])).status_code, 404)

    def test_previews_never_send_or_save(self):
        self.client.get(reverse("email_preview_body", args=["s135_notice", "html"]))
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Incident.objects.exists())

    def test_non_staff_are_sent_to_admin_login(self):
        self.client.force_login(make_user())
        response = self.client.get(reverse("email_preview_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])


class SidebarTests(TestCase):
    def setUp(self):
        self.strata = make_strata()
        self.user = make_user()
        make_membership(self.user, self.strata)
        self.client.force_login(self.user)

    def main_nav(self, url):
        html = self.client.get(url).content.decode()
        return re.search(r'<nav\s+aria-label="Main".*?</nav>', html, re.S).group(0)

    def test_groups_pages_by_pillar_and_marks_only_the_current_page(self):
        nav = self.main_nav(reverse("dockets:incident_list"))

        for group in ("Work", "Enforcement", "Money", "Records", "Building"):
            self.assertIn(f">{group}</p>", nav)
        current = re.findall(r'href="([^"]+)"\s+aria-current="page"', nav)
        self.assertEqual(current, [reverse("dockets:incident_list")])

    def test_unbuilt_pillars_are_labels_not_links(self):
        nav = self.main_nav(reverse("dashboard"))

        self.assertIn('title="Projects is coming soon"', nav)
        self.assertNotIn('href="#"', nav)

    def test_billing_is_not_in_the_nav_for_any_role(self):
        manager = make_user()
        make_membership(manager, self.strata, role=Membership.Role.MANAGER)

        for user in (self.user, manager):
            self.client.force_login(user)
            nav = self.main_nav(reverse("dashboard"))
            self.assertNotIn(reverse("payments:subscription_dashboard"), nav)
            self.assertIn(reverse("dockets:voting_center"), nav)


class ListboxTests(TestCase):
    def test_form_fields_render_as_listbox_with_value_and_safe_labels(self):
        from django import forms
        from django.template import Context, Template

        class F(forms.Form):
            owner = forms.ChoiceField(choices=[("", "Nobody yet"), ("1", "Pat O'Brien")])

        from django_cotton.compiler_regex import CottonCompiler

        source = CottonCompiler().process('<c-listbox :field="form.owner" />')  # cotton compiles file templates only
        html = Template(source).render(Context({"form": F(initial={"owner": "1"})}))
        self.assertIn('name="owner"', html)
        self.assertIn("selected: '1'", html)
        self.assertIn("Pat O’Brien", html)  # a straight apostrophe would break cotton-ui's inline JavaScript
        self.assertNotIn("O'Brien", html)
        self.assertNotIn("<select", html)
