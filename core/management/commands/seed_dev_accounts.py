from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.dev import DEV_ACCOUNTS, ensure_dev_accounts


class Command(BaseCommand):
    help = "Create or repair the fixed local accounts (admin, manager, president, treasurer, newcomer). DEBUG only."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Refusing to create known-password accounts with DEBUG off.")
        ensure_dev_accounts()
        for key, spec in DEV_ACCOUNTS.items():
            self.stdout.write(f"  {spec['label']:<18} {spec['email']}")
        self.stdout.write(self.style.SUCCESS(
            "Dev accounts ready. Password: DEV_ACCOUNT_PASSWORD in .env. "
            "Or use the 'Log in as' buttons on the login page."
        ))
