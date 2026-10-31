"""
Every email the app sends flows through here.

- EMAILS is the registry: one entry per email type (subject + template + tag).
  Add a new email by adding an entry and a template in core/templates/emails/.
- send() renders the HTML template (plain text is derived from it), applies shared
  settings (from address, reply-to, site URL, Resend tags) and delivers through anymail.

Settings used: DEFAULT_FROM_EMAIL, EMAIL_REPLY_TO, SITE_URL (all in config/settings.py, from .env).
"""
import logging
import re
from dataclasses import dataclass
from html import unescape

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailType:
    subject: str    # Django template string, rendered with the same context as the body
    template: str   # core/templates/emails/<template>.html
    tag: str        # Resend tag, for filtering in the Resend dashboard


EMAILS = {
    # Accounts
    "welcome": EmailType("Welcome to CivicDesk", "welcome", "welcome"),
    "password_reset": EmailType("Reset your CivicDesk password", "password_reset", "password-reset"),
    "unknown_account": EmailType("CivicDesk password reset request", "unknown_account", "password-reset"),
    # Membership approval
    "membership_requested": EmailType(
        "Approval needed: {{ membership.user.email }} → {{ membership.strata.plan_number }}",
        "membership_requested", "membership",
    ),
    "membership_approved": EmailType(
        "You're approved for {{ membership.strata.plan_number }} on CivicDesk", "membership_approved", "membership",
    ),
    "membership_rejected": EmailType(
        "Your CivicDesk request for {{ membership.strata.plan_number }}", "membership_rejected", "membership",
    ),
    # Bylaw enforcement (dockets)
    "docket_logged": EmailType(
        "New docket for {{ incident.strata.plan_number }}: {{ incident.title }}", "docket_logged", "docket",
    ),
    "s135_notice": EmailType(
        "FORMAL NOTICE OF COMPLAINT - {{ incident.strata.plan_number }}", "s135_notice", "s135-notice",
    ),
    "voting_open": EmailType(
        "Council vote needed: {{ incident.title }}", "voting_open", "docket",
    ),
    "decision_reached": EmailType(
        "Council decision: {{ incident.title }} ({{ incident.get_status_display }})", "decision_reached", "docket",
    ),
    "fine_notice": EmailType(
        "Notice of Formal Fine - Strata Plan {{ incident.strata.plan_number }}", "fine_notice", "fine-notice",
    ),
    # Documents & inbox (AI)
    "document_summarized": EmailType("Summary ready: {{ document.title }}", "document_summarized", "documents"),
    "inbound_summarized": EmailType("Summary: {{ email.summary.title|default:email.subject }}", "inbound_summarized", "inbox"),
}


def send(key, to, context=None, *, reply_to=None, fail_silently=True):
    """
    Send email `key` to each address in `to` (one private copy per recipient).
    Returns True when every copy was handed to the provider.
    With fail_silently=False, delivery errors propagate (use for legally significant notices).
    """
    spec = EMAILS[key]
    recipients = [addr for addr in dict.fromkeys(to) if addr]
    if not recipients:
        return False

    subject, text, html = render(key, context)
    reply_to = reply_to or ([settings.EMAIL_REPLY_TO] if settings.EMAIL_REPLY_TO else None)

    all_sent = True
    for recipient in recipients:
        message = EmailMultiAlternatives(
            subject=subject, body=text, from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient], reply_to=reply_to,
        )
        message.attach_alternative(html, "text/html")
        message.tags = [spec.tag]  # anymail -> Resend tags
        try:
            message.send()
        except Exception:
            logger.exception("Email %s to %s failed", key, recipient)
            if not fail_silently:
                raise
            all_sent = False
    return all_sent


def render(key, context=None):
    """(subject, text, html) for email `key`. Used by send() and the staff preview page."""
    spec = EMAILS[key]
    context = {"site_url": settings.SITE_URL.rstrip("/"), **(context or {})}
    subject = _one_line(Template(spec.subject).render(Context(context)))
    html = render_to_string(f"emails/{spec.template}.html", context)
    return subject, _html_to_text(html), html


def _one_line(text):
    return re.sub(r"\s+", " ", text).strip()


def _html_to_text(html):
    text = re.sub(r"<(br|/p|/div|/h\d|/li|/tr)[^>]*>", "\n", html, flags=re.I)
    text = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", text, flags=re.I | re.S)
    text = unescape(strip_tags(text))
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()
