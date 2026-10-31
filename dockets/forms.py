from django import forms

from .models import IncidentEvent


class IncidentEventForm(forms.ModelForm):
    """Timeline entries members may add by hand. System events (notices, owner responses, fines) are excluded."""
    MANUAL_TYPES = [
        IncidentEvent.EventType.NOTE,
        IncidentEvent.EventType.RECURRENCE,
        IncidentEvent.EventType.EVIDENCE,
    ]

    event_type = forms.ChoiceField(choices=[(t.value, t.label) for t in MANUAL_TYPES])

    class Meta:
        model = IncidentEvent
        fields = ['event_type', 'description', 'evidence_file']
