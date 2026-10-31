from anymail.signals import inbound
from django.dispatch import receiver

from . import services


@receiver(inbound)
def handle_inbound_email(sender, event, esp_name, **kwargs):
    """anymail verified the webhook and fetched the message; hand it to the inbox."""
    message = event.message
    if message is None:
        return
    data_to = (event.esp_event or {}).get("data", {}).get("to") or []
    recipients = [a.addr_spec for a in [*message.to, *message.cc]] + list(data_to)
    services.receive_message(message, recipients, event_id=event.event_id)
