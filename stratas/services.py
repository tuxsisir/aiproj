"""
Membership lifecycle: request -> (platform admin) approve / reject -> leave.
Views and admin call these; they hold no request-handling logic.
"""
from django.contrib.auth import get_user_model
from django.utils import timezone

from core import emails
from .models import Membership, StrataPlan


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
    emails.send("membership_approved", [membership.user.email], {"membership": membership})


def reject_membership(membership, reviewer):
    _review(membership, reviewer, Membership.Status.REJECTED)
    emails.send("membership_rejected", [membership.user.email], {"membership": membership})


def leave_strata(membership):
    """Deactivate instead of delete so votes and history stay linked to the member."""
    membership.status = Membership.Status.INACTIVE
    membership.save(update_fields=["status", "updated_at"])


def member_emails(strata, role=None):
    """Emails of active members of a building, optionally only one role."""
    members = Membership.objects.active().filter(strata=strata)
    if role:
        members = members.filter(role=role)
    return list(members.values_list("user__email", flat=True))


def create_strata(plan_number, name, created_by):
    return StrataPlan.objects.create(plan_number=plan_number, name=name, created_by=created_by)


def _review(membership, reviewer, status):
    membership.status = status
    membership.reviewed_by = reviewer
    membership.reviewed_at = timezone.now()
    membership.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])


def _notify_platform_admins(membership):
    admin_emails = (
        get_user_model().objects.filter(is_superuser=True, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )
    emails.send("membership_requested", list(admin_emails), {"membership": membership})
