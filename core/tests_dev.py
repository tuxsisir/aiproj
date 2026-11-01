from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import include, path, reverse

from core.dev import DEV_ACCOUNTS, ensure_dev_accounts, login_as
from core.models import User
from stratas.models import Membership

# Tests run with DEBUG off, so config.urls leaves the dev route out (as in production).
urlpatterns = [
    path("__debug__/", include("debug_toolbar.urls")),  # toolbar activates when a test forces DEBUG on
    path("dev/login-as/<str:key>/", login_as, name="dev_login_as"),
    path("", include("config.urls")),
]


@override_settings(ROOT_URLCONF="core.tests_dev")
class DevAccountTests(TestCase):
    def test_accounts_are_idempotent_with_expected_roles(self):
        ensure_dev_accounts()
        users = ensure_dev_accounts()
        self.assertEqual(User.objects.filter(email__endswith="@civicdesk.test").count(), len(DEV_ACCOUNTS))
        self.assertTrue(users["admin"].is_superuser)
        self.assertFalse(users["admin"].memberships.exists())
        treasurer = users["treasurer"].memberships.get()
        self.assertEqual((treasurer.position, treasurer.status), (Membership.Position.TREASURER, Membership.Status.ACTIVE))
        self.assertEqual(users["newcomer"].memberships.get().status, Membership.Status.PENDING)
        self.assertTrue(users["manager"].memberships.get().is_manager)

    def test_legacy_demo_emails_are_renamed(self):
        User.objects.create_user(username="council", email="council@council.com")
        ensure_dev_accounts()
        self.assertFalse(User.objects.filter(email="council@council.com").exists())
        self.assertEqual(User.objects.filter(email="president@civicdesk.test").count(), 1)

    @override_settings(DEBUG=True)
    def test_login_as_treasurer_lands_on_dashboard(self):
        response = self.client.post(reverse("dev_login_as", args=["treasurer"]), follow=True)
        self.assertEqual(response.wsgi_request.user.email, "treasurer@civicdesk.test")
        self.assertEqual(response.wsgi_request.membership.position, Membership.Position.TREASURER)

    @override_settings(DEBUG=True)
    def test_login_as_admin_goes_to_admin(self):
        response = self.client.post(reverse("dev_login_as", args=["admin"]))
        self.assertRedirects(response, reverse("admin:index"))

    @override_settings(DEBUG=True)
    def test_switch_panel_shown_on_login_page_in_debug(self):
        self.assertContains(self.client.get(reverse("account_login")), "Local dev · log in as")

    def test_disabled_when_debug_off(self):
        self.assertEqual(self.client.post(reverse("dev_login_as", args=["admin"])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("account_login")), "Local dev · log in as")
        with self.assertRaises(CommandError):
            call_command("seed_dev_accounts")

    @override_settings(DEBUG=True)
    def test_get_and_unknown_keys_are_rejected(self):
        self.assertEqual(self.client.get(reverse("dev_login_as", args=["admin"])).status_code, 405)
        self.assertEqual(self.client.post(reverse("dev_login_as", args=["root"])).status_code, 404)
