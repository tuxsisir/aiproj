from django import forms

from issues.forms import INPUT_CLASS, member_choices
from .models import AgendaItem, Meeting


class LinkedChoiceField(forms.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple


class MeetingForm(forms.ModelForm):
    """Plan a meeting. Open issues and enforcement cases are offered as agenda items, all ticked by default."""

    issues = LinkedChoiceField(queryset=None, required=False, label="Building issues")
    cases = LinkedChoiceField(queryset=None, required=False, label="Enforcement cases (in camera)")

    class Meta:
        model = Meeting
        fields = ["kind", "starts_at", "location"]
        widgets = {
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "location": forms.TextInput(attrs={"placeholder": "e.g. Amenity room, or a video call link"}),
        }
        labels = {"kind": "Meeting", "starts_at": "Date and time"}

    def __init__(self, *args, issues, cases, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["issues"].queryset, self.fields["cases"].queryset = issues, cases
        self.fields["issues"].label_from_instance = lambda issue: issue.title
        self.fields["cases"].label_from_instance = (
            lambda case: f"Unit {case.unit_number}: {case.title}" if case.unit_number else case.title
        )
        if not self.is_bound:
            self.initial.update(issues=list(issues), cases=list(cases))
        for name in ["kind", "starts_at", "location"]:
            self.fields[name].widget.attrs["class"] = INPUT_CLASS


class AgendaItemForm(forms.ModelForm):
    class Meta:
        model = AgendaItem
        fields = ["title", "details", "in_camera"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. Gutter cleaning quotes"}),
            "details": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2, "placeholder": "Optional background"}),
        }
        labels = {"in_camera": "In camera (left out of the owners' copy of the minutes)"}


class MinutesForm(forms.ModelForm):
    class Meta:
        model = AgendaItem
        fields = ["minutes", "decision"]
        widgets = {
            "minutes": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2, "placeholder": "What was discussed"}),
            "decision": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2,
                                              "placeholder": "Motion or decision, if any"}),
        }


class HeldForm(forms.Form):
    attendees = forms.ModelMultipleChoiceField(queryset=None, widget=forms.CheckboxSelectMultiple,
                                               label="Present")
    guests = forms.CharField(max_length=255, required=False, label="Also present",
                             widget=forms.TextInput(attrs={"class": INPUT_CLASS,
                                                           "placeholder": "e.g. Owner of unit 1204 (hearing)"}))

    def __init__(self, *args, meeting, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields["attendees"]
        field.queryset = member_choices(meeting.strata)
        field.label_from_instance = lambda user: user.get_full_name() or user.email
        if not self.is_bound:
            self.initial["attendees"] = list(field.queryset)


class MoveForm(forms.Form):
    direction = forms.ChoiceField(choices=[("up", "Up"), ("down", "Down")])
