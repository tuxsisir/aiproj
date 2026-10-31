import re

from django import forms

from .models import Membership, StrataPlan

BC_PLAN_NUMBER = re.compile(r'^(EPS|BCS|LMS|NWS|VIS|KAS|PRS)\s?\d{1,6}$')


class OnboardingForm(forms.Form):
    """Join an existing building or register a new one. The result is always a PENDING request."""
    persona = forms.ChoiceField(choices=Membership.Role.choices)
    strata_id = forms.ModelChoiceField(queryset=StrataPlan.objects.all(), required=False)
    plan_number = forms.CharField(max_length=30, required=False)
    name = forms.CharField(max_length=150, required=False)
    position = forms.ChoiceField(choices=Membership.Position.choices, required=False)
    unit_number = forms.CharField(max_length=10, required=False)
    phone_number = forms.CharField(max_length=30, required=False)
    brokerage_name = forms.CharField(max_length=150, required=False)

    def clean_plan_number(self):
        plan_number = self.cleaned_data['plan_number'].strip().upper()
        return plan_number.replace(" ", "")

    def clean(self):
        cleaned = super().clean()
        is_council = cleaned.get('persona') == Membership.Role.COUNCIL

        if not cleaned.get('strata_id'):
            plan_number = cleaned.get('plan_number', '')
            if not BC_PLAN_NUMBER.match(plan_number):
                self.add_error('plan_number', "Invalid Strata Plan format. Must be EPS, BCS, etc. followed by numbers.")
            elif StrataPlan.objects.filter(plan_number=plan_number).exists():
                self.add_error('plan_number', f"Strata Plan {plan_number} already exists. Please select it from the list instead.")
            if not cleaned.get('name', '').strip():
                self.add_error('name', "Building name is required.")

        if is_council:
            if not cleaned.get('position'):
                self.add_error('position', "Select your council position.")
            if not cleaned.get('unit_number', '').strip():
                self.add_error('unit_number', "Unit number is required for council members.")
        elif not cleaned.get('brokerage_name', '').strip():
            self.add_error('brokerage_name', "Brokerage name is required for managers.")

        return cleaned
