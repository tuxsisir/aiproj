from django import forms
from django.contrib.auth import get_user_model

from stratas.models import Membership
from .models import Issue

INPUT_CLASS = (
    "w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 "
    "px-3 py-2 text-sm text-slate-900 dark:text-slate-100"
)


def member_choices(strata):
    """Active council members and managers of this building: the only people an issue can be assigned to."""
    users = Membership.objects.active().filter(strata=strata).values("user_id")
    return get_user_model().objects.filter(pk__in=users).order_by("first_name", "email")


class AssigneeField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        return user.get_full_name() or user.email


class IssueForm(forms.ModelForm):
    assigned_to = AssigneeField(queryset=None, required=False, empty_label="Nobody yet", label="Owner")

    class Meta:
        model = Issue
        fields = ["title", "description", "location", "category", "priority", "assigned_to", "vendor", "due_date"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. Storage room 5 door doesn't latch"}),
            "description": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 4,
                                                 "placeholder": "What's wrong, since when, who noticed"}),
            "location": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. Parkade P1, storage room 5"}),
            "category": forms.Select(attrs={"class": INPUT_CLASS}),
            "priority": forms.Select(attrs={"class": INPUT_CLASS}),
            "vendor": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Optional, e.g. ABC Locksmith"}),
            "due_date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}, format="%Y-%m-%d"),
        }
        labels = {"due_date": "Fix by", "assigned_to": "Owner"}

    def __init__(self, *args, strata, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = member_choices(strata)
        self.fields["assigned_to"].widget.attrs["class"] = INPUT_CLASS


class IssueUpdateForm(forms.Form):
    """Move an issue along: status, owner, fix-by date, vendor and/or a comment, in one submit."""

    status = forms.ChoiceField(choices=Issue.Status.choices)
    assigned_to = AssigneeField(queryset=None, required=False, empty_label="Nobody", label="Owner")
    due_date = forms.DateField(required=False, label="Fix by",
                               widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    vendor = forms.CharField(max_length=120, required=False)
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Optional"}))
    outcome = forms.CharField(required=False, label="Outcome",
                              widget=forms.Textarea(attrs={"rows": 2, "placeholder": "How it was resolved"}))

    def __init__(self, *args, issue, **kwargs):
        initial = {"status": issue.status, "assigned_to": issue.assigned_to_id, "due_date": issue.due_date,
                   "vendor": issue.vendor, "outcome": issue.outcome}
        super().__init__(*args, initial=initial, **kwargs)
        self.issue = issue
        # A former member can stay the owner until someone reassigns it; only active members can be picked anew.
        self.fields["assigned_to"].queryset = (member_choices(issue.strata) | get_user_model().objects.filter(
            pk=issue.assigned_to_id)).distinct().order_by("first_name", "email")
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        closing = data["status"] in Issue.CLOSED and self.issue.is_open
        if closing and not data.get("outcome", "").strip():
            self.add_error("outcome", "Say how it was resolved (or why no action) before closing.")
        changed = (
            data["status"] != self.issue.status
            or data.get("assigned_to") != self.issue.assigned_to
            or data.get("due_date") != self.issue.due_date
            or data.get("vendor", "") != self.issue.vendor
            or data.get("comment", "").strip()
        )
        if not changed:
            raise forms.ValidationError("Nothing to update: change something or add a comment.")
        return data


class IssueFilterForm(forms.Form):
    show = forms.ChoiceField(choices=[("open", "Open"), ("mine", "Mine"), ("closed", "Closed"), ("all", "All")],
                             required=False)
