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


class Membership(BaseModel):
    """
    RBAC Bridge connecting any User to any StrataPlan.
    Allows council members to bind to 1 building, and strata managers to bind to many.
    """
    class Role(models.TextChoices):
        COUNCIL_PRESIDENT = 'PRESIDENT', 'Council President / Chair'
        COUNCIL_MEMBER    = 'COUNCIL',   'Council Member'
        STRATA_MANAGER    = 'MANAGER',   'Licensed Strata Manager'
        CARETAKER         = 'CARETAKER', 'Building Caretaker / Staff'

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
        default=Role.COUNCIL_MEMBER
    )
    
    # Specific unit number (crucial for council members who are unit owners)
    unit_number = models.CharField(max_length=10, blank=True, help_text="Unit / Lot number owned or occupied")
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'strata')
        indexes = [
            models.Index(fields=['user', 'strata', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user.email} -> {self.strata.plan_number} ({self.get_role_display()})"


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
