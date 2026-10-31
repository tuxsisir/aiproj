"""
Inbound email flow: provider webhook -> receive_message() -> background summary -> reply to forwarder.
Only emails forwarded by an active member of the building are accepted.
"""
import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils.html import strip_tags

from core import ai as core_ai, emails
from core.background import run_after_commit
from stratas.models import Membership
from . import ai
from .models import InboundEmail, Inbox

logger = logging.getLogger(__name__)


def get_or_create_inbox(strata):
    inbox = Inbox.objects.filter(strata=strata).first()
    return inbox or Inbox.objects.create(strata=strata, local_part=Inbox.new_local_part(strata))


def find_inbox(addresses):
    """The building inbox addressed by any of `addresses` (to/cc/envelope), or None."""
    domain = settings.INBOUND_EMAIL_DOMAIN.lower()
    local_parts = [
        addr.lower().rsplit("@", 1)[0] for addr in addresses if addr and addr.lower().endswith("@" + domain)
    ]
    return Inbox.objects.select_related("strata").filter(local_part__in=local_parts).first()


def receive_message(message, recipients, event_id=None):
    """
    Store a forwarded email and queue its summary. Returns the InboundEmail, or None when ignored
    (unknown inbox, sender isn't an active member, or duplicate delivery).
    """
    inbox = find_inbox(recipients)
    if inbox is None:
        logger.info("Inbound email for unknown inbox: %s", recipients)
        return None

    sender = message.from_email.addr_spec if message.from_email else ""
    membership = (
        Membership.objects.active().select_related("user")
        .filter(strata=inbox.strata, user__email__iexact=sender).first()
    )
    if membership is None:
        logger.info("Inbound email to %s from non-member %s ignored", inbox.address, sender)
        return None

    try:
        with transaction.atomic():
            email = InboundEmail.objects.create(
                strata=inbox.strata,
                forwarded_by=membership.user,
                provider_event_id=event_id or None,
                from_email=sender,
                from_name=message.from_email.display_name or "",
                subject=(message.subject or "")[:500],
                body_text=message.text or strip_tags(message.html or ""),
                attachments=[
                    {
                        "filename": part.get_filename() or "attachment",
                        "content_type": part.get_content_type(),
                        "size": len(part.get_content_bytes() or b""),
                    }
                    for part in message.attachments
                ],
            )
    except IntegrityError:
        logger.info("Duplicate inbound event %s ignored", event_id)
        return None

    queue_summary(email)
    return email


def queue_summary(email):
    if not core_ai.is_configured():
        _fail(email, "AI isn't set up yet. Add ANTHROPIC_API_KEY, then retry.")
        return
    run_after_commit(_summarize_by_pk, email.pk)


def _summarize_by_pk(email_pk):
    summarize(InboundEmail.objects.get(pk=email_pk))


def summarize(email):
    """Generate and store the summary, then email it back to whoever forwarded it. Never raises."""
    email.status = InboundEmail.Status.PROCESSING
    email.error = ""
    email.save(update_fields=["status", "error", "updated_at"])
    try:
        email.summary = ai.summarize_email(
            email.subject,
            f"{email.from_name} <{email.from_email}>".strip(),
            email.body_text,
            [a["filename"] for a in email.attachments],
        )
    except ai.AIError as exc:
        _fail(email, str(exc))
        return email
    except Exception:
        logger.exception("Summarizing inbound email %s failed", email.pk)
        _fail(email, "Something went wrong while summarizing. Try again.")
        return email

    email.status = InboundEmail.Status.READY
    email.save(update_fields=["summary", "status", "updated_at"])
    if email.forwarded_by:
        emails.send("inbound_summarized", [email.forwarded_by.email], {"email": email})
    return email


def _fail(email, message):
    email.status = InboundEmail.Status.FAILED
    email.error = message[:255]
    email.save(update_fields=["status", "error", "updated_at"])
