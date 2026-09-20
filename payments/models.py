from django.db import models
from django.conf import settings

class UserSubscription(models.Model):
    """
    Local mirror of a user's Stripe subscription state.
    We don't hold the payment methods, invoices, etc., just the basic status
    to quickly allow or deny access to views without querying Stripe on every request.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription"
    )
    stripe_customer_id = models.CharField(max_length=255, null=True, blank=True)
    stripe_subscription_id = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, default="inactive")
    current_period_end = models.DateTimeField(null=True, blank=True)

    @property
    def is_active(self):
        """Returns True if the user has an active or trialing subscription."""
        return self.status in ['active', 'trialing']

    def __str__(self):
        return f"{self.user.username} - {self.status}"
