"""Simulate a forwarded email locally (no Resend needed): runs the same path as the webhook."""
import uuid
from pathlib import Path

from anymail.inbound import AnymailInboundMessage
from django.core.management.base import BaseCommand, CommandError

from inbox import services
from stratas.models import StrataPlan


class Command(BaseCommand):
    help = "Forward an email thread (text file) into a building's inbox, then summarize it inline."

    def add_arguments(self, parser):
        parser.add_argument("plan_number", help="e.g. EPS123")
        parser.add_argument("sender", help="Email of an active member of that building")
        parser.add_argument("thread_file", help="Path to a .txt file with the email thread")
        parser.add_argument("--subject", default="Fwd: building issue")

    def handle(self, plan_number, sender, thread_file, subject, **options):
        strata = next(
            (s for s in StrataPlan.objects.all() if s.plan_number.replace(" ", "").upper() == plan_number.replace(" ", "").upper()),
            None,
        )
        if strata is None:
            raise CommandError(f"No building with plan number {plan_number}")
        inbox = services.get_or_create_inbox(strata)
        message = AnymailInboundMessage.construct(
            from_email=sender, to=inbox.address, subject=subject, text=Path(thread_file).read_text(),
        )
        email = services.receive_message(message, [inbox.address], event_id=f"sim-{uuid.uuid4()}")
        if email is None:
            raise CommandError(f"Ignored: {sender} isn't an active member of {strata.plan_number}")
        email.refresh_from_db()
        if email.status != email.Status.FAILED:
            services.summarize(email)  # inline instead of the background thread
            email.refresh_from_db()
        self.stdout.write(f"{email.status}: {email.title} -> /inbox/{email.pk}/")
        if email.error:
            self.stdout.write(self.style.WARNING(email.error))
