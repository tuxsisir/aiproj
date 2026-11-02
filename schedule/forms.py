import datetime

from django import forms

from .models import KeyDate

INPUT_CLASS = (
    "w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 "
    "px-3 py-2 text-sm text-slate-900 dark:text-slate-100"
)


class MonthForm(forms.Form):
    """?month=2026-11 on the calendar page."""

    month = forms.RegexField(regex=r"^\d{4}-(0[1-9]|1[0-2])$", required=False)

    def first_day(self, today):
        value = self.is_valid() and self.cleaned_data.get("month")
        if not value:
            return today.replace(day=1)
        year, month = map(int, value.split("-"))
        if not 2000 <= year <= 2100:
            return today.replace(day=1)
        return datetime.date(year, month, 1)


class KeyDateForm(forms.ModelForm):
    class Meta:
        model = KeyDate
        fields = ["title", "date", "category", "repeats_yearly", "note"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. Insurance renewal"}),
            "date": forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}, format="%Y-%m-%d"),
            "category": forms.Select(attrs={"class": INPUT_CLASS}),
            "note": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3, "placeholder": "Optional details"}),
        }
        labels = {"repeats_yearly": "Repeats every year"}
