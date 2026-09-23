import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models


class BaseModel(models.Model):
    """
    Abstract base model providing UUID primary key, 
    creation, and update timestamps.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class User(AbstractUser):
    """Custom User Model for the base project."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    brokerage_name = models.CharField(max_length=150, blank=True)
    
    def __str__(self):
        return self.username
