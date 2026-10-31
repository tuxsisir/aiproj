"""
Membership lifecycle: request -> (platform admin) approve / reject -> leave.
Views and admin call these; they hold no request-handling logic.
"""
import logging

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from .models import Membership, StrataPlan

logger = logging.getLogger(__name__)


def request_membership(user, strata, role, position="", unit_number=""):
    """Create (or re-open) a PENDING membership. Active memberships are left untouched."""
    membership, created = Membership.objects.get_or_create(
        user=user,
        strata=strata,
        defaults={"role": role, "position": position, "unit_number": unit_number},
    )
    if not created and membership.status == Membership.Status.ACTIVE:
        return membership

    if not created:
        membership.role = role
        membership.position = position
        membership.unit_number = unit_number
        membership.status = Membership.Status.PENDING
        membership.reviewed_by = None
        membership.reviewed_at = None
        membership.save()

    _notify_platform_admins(membership)
    return membership


def approve_membership(membership, reviewer):
    _review(membership, reviewer, Membership.Status.ACTIVE)
    _notify(
        membership.user.email,
        f"You're approved for {membership.strata.plan_number} on CivicDesk",
        f"Your access to {membership.strata} as {membership.title} has been approved. "
        "Sign in to get started.",
    )


def reject_membership(membership, reviewer):
    _review(membership, reviewer, Membership.Status.REJECTED)
    _notify(
        membership.user.email,
        f"Your CivicDesk request for {membership.strata.plan_number}",
        f"Your request to join {membership.strata} was not approved. "
        "Reply to this email if you think this is a mistake.",
    )


def leave_strata(membership):
    """Deactivate instead of delete so votes and history stay linked to the member."""
    membership.status = Membership.Status.INACTIVE
    membership.save(update_fields=["status", "updated_at"])


def create_strata(plan_number, name, created_by):
    return StrataPlan.objects.create(plan_number=plan_number, name=name, created_by=created_by)


def _review(membership, reviewer, status):
    membership.status = status
    membership.reviewed_by = reviewer
    membership.reviewed_at = timezone.now()
    membership.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])


def _notify_platform_admins(membership):
    admin_emails = list(
        get_user_model().objects.filter(is_superuser=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    if not admin_emails:
        return
    _notify(
        admin_emails,
        f"Approval needed: {membership.user.email} -> {membership.strata.plan_number}",
        f"{membership.user.get_full_name() or membership.user.email} requested access to "
        f"{membership.strata} as {membership.title}. Review it in the admin under Memberships.",
    )


def _notify(recipients, subject, message):
    if isinstance(recipients, str):
        recipients = [recipients]
    try:
        send_mail(subject, message, None, recipients)
    except Exception:
        # Email must never block onboarding or approval; log and move on.
        logger.exception("Failed to send membership email: %s", subject)
