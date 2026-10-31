from allauth.account.signals import user_signed_up
from django.dispatch import receiver

from core import emails


@receiver(user_signed_up)
def send_welcome_email(request, user, **kwargs):
    emails.send("welcome", [user.email], {"user": user})
