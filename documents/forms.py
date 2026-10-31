from django import forms

from .models import Document

MAX_UPLOAD_BYTES = 32 * 1024 * 1024
INPUT_CLASS = (
    "w-full rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 "
    "px-3 py-2 text-sm text-slate-900 dark:text-slate-100"
)


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ["title", "category", "file"]
        widgets = {
            "title": forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "e.g. Bylaws (consolidated 2024)"}),
            "category": forms.Select(attrs={"class": INPUT_CLASS}),
            "file": forms.ClearableFileInput(attrs={"class": "w-full text-sm text-slate-600 dark:text-slate-300", "accept": "application/pdf"}),
        }

    def clean_file(self):
        f = self.cleaned_data["file"]
        if f.size > MAX_UPLOAD_BYTES:
            raise forms.ValidationError("PDFs must be 32 MB or smaller.")
        header = f.read(5)
        f.seek(0)
        if header != b"%PDF-":
            raise forms.ValidationError("That file isn't a PDF.")
        return f


class QuestionForm(forms.Form):
    question = forms.CharField(max_length=500, strip=True)
