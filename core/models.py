import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from pgvector.django import VectorField


class Company(models.Model):
    """Boutique Property Management agency profile."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class StrataCorp(models.Model):
    """The individual building/townhouse tenant instance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="strata_corps"
    )
    strata_plan_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return (
            f"{self.strata_plan_number} - {self.name}"
            if self.name
            else self.strata_plan_number
        )


class User(AbstractUser):
    """Custom User Model linked to StrataCorp."""

    class Role(models.TextChoices):
        RESIDENT = "resident", "Resident"
        COUNCIL = "council", "Council"
        MANAGER = "manager", "Manager"
        SUPERADMIN = "superadmin", "Superadmin"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    strata_corp = models.ForeignKey(
        StrataCorp,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RESIDENT)

    def __str__(self):
        return self.username


class Document(models.Model):
    """Uploaded PDFs of bylaws/minutes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    strata_corp = models.ForeignKey(
        StrataCorp, on_delete=models.CASCADE, related_name="documents"
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    is_confidential = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class DocumentChunk(models.Model):
    """Extracted text from documents."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="chunks"
    )
    page_number = models.IntegerField()
    text = models.TextField()
    embedding = VectorField(dimensions=1536)

    def __str__(self):
        return f"Chunk from {self.document.title} - Page {self.page_number}"


class InteractionLog(models.Model):
    """Secure audit for resident queries."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="interactions"
    )
    strata_corp = models.ForeignKey(
        StrataCorp, on_delete=models.CASCADE, related_name="interactions"
    )
    raw_query = models.TextField()
    response = models.TextField()
    sources = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Query by {self.user} at {self.created_at}"
