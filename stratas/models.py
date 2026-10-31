import uuid
from django.db import models
from django.conf import settings
from core.models import BaseModel

class StrataPlan(BaseModel):
    """
    The Legal Entity & Tenant Boundary.
    Represents a registered Strata Corporation, Condo Corporation, or HOA.
    """
    # Primary legal identifier (e.g., EPS 412, BCS 1024, TS 89)
    plan_number = models.CharField(
        max_length=30, 
        unique=True, 
        db_index=True,
        help_text="Official plan identifier registered with the land authority (e.g. EPS 412)"
    )
    name = models.CharField(
        max_length=150, 
        help_text="Building or complex trade name (e.g. Kingsview Manor)"
    )
    
    # Universal North American Address Architecture
    street_address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state_province = models.CharField(max_length=50, default="BC", help_text="e.g. BC, ON, WA, FL")
    postal_code = models.CharField(max_length=20, help_text="Postal Code or ZIP")
    country = models.CharField(max_length=2, default="CA", help_text="ISO 2-letter country code (CA, US)")
    
    total_units = models.PositiveIntegerField(default=1, help_text="Total number of registered strata lots")
    
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="created_stratas"
    )

    class Meta:
        verbose_name = "Strata Plan"
        verbose_name_plural = "Strata Plans"
        ordering = ["plan_number"]

    def __str__(self):
        return f"{self.plan_number} - {self.name}"


class MembershipQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=Membership.Status.ACTIVE)

    def pending(self):
        return self.filter(status=Membership.Status.PENDING)

    def council(self):
        return self.filter(role=Membership.Role.COUNCIL)

    def managers(self):
        return self.filter(role=Membership.Role.MANAGER)


class Membership(BaseModel):
    """
    RBAC Bridge connecting any User to any StrataPlan.
    Allows council members to bind to 1 building, and strata managers to bind to many.

    `role` drives permissions; `position` is the council office held (display / future per-office rights).
    New memberships start PENDING and need platform-admin approval (see stratas.services).
    """
    class Role(models.TextChoices):
        COUNCIL = 'COUNCIL', 'Council Member'
        MANAGER = 'MANAGER', 'Strata Manager'

    class Position(models.TextChoices):
        PRESIDENT = 'PRESIDENT', 'President'
        VICE_PRESIDENT = 'VICE_PRESIDENT', 'Vice-President'
        TREASURER = 'TREASURER', 'Treasurer'
        SECRETARY = 'SECRETARY', 'Secretary'
        MEMBER_AT_LARGE = 'MEMBER_AT_LARGE', 'Member-at-Large'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        ACTIVE = 'ACTIVE', 'Active'
        REJECTED = 'REJECTED', 'Rejected'
        INACTIVE = 'INACTIVE', 'Inactive'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="memberships"
    )
    strata = models.ForeignKey(
        StrataPlan, 
        on_delete=models.CASCADE, 
        related_name="memberships"
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.COUNCIL
    )
    position = models.CharField(max_length=20, choices=Position.choices, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    # Specific unit number (crucial for council members who are unit owners)
    unit_number = models.CharField(max_length=10, blank=True, help_text="Unit / Lot number owned or occupied")
    joined_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_memberships"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        unique_together = ('user', 'strata')
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['strata', 'status']),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.strata.plan_number} ({self.title})"

    @property
    def is_council(self):
        return self.role == self.Role.COUNCIL

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def title(self):
        """Human label, e.g. 'Treasurer' or 'Strata Manager'."""
        return self.get_position_display() if self.position else self.get_role_display()


class StrataInvitation(BaseModel):
    """
    Secure tokenized invitations to onboard co-council members or licensed managers.
    """
    strata = models.ForeignKey(
        StrataPlan, 
        on_delete=models.CASCADE, 
        related_name="invitations"
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name="sent_invitations"
    )
    email = models.EmailField()
    role = models.CharField(max_length=20, choices=Membership.Role.choices)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_accepted = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite for {self.email} to {self.strata.plan_number} ({self.get_role_display()})"
