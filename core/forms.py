from django import forms

class CustomSignupForm(forms.Form):
    first_name = forms.CharField(max_length=30, label='First Name', widget=forms.TextInput(attrs={'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=30, label='Last Name', widget=forms.TextInput(attrs={'placeholder': 'Last Name'}))
    field_order = ['first_name', 'last_name', 'email', 'password1']

    def signup(self, request, user):
        pass
