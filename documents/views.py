from itertools import groupby

from django.contrib import messages
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from stratas.decorators import membership_required
from . import ai, services
from .forms import DocumentUploadForm, QuestionForm
from .models import Document, DocumentQuestion


def _get_document(request, pk):
    return get_object_or_404(Document, pk=pk, strata=request.strata)


@membership_required
def document_library(request):
    documents = request.strata.documents.select_related("uploaded_by")
    grouped = [
        (Document.Category(category).label, list(docs))
        for category, docs in groupby(documents, key=lambda d: d.category)
    ]
    return render(request, "documents/library.html", {
        "grouped_documents": grouped,
        "has_documents": bool(grouped),
        "recent_questions": request.strata.document_questions.select_related("asked_by")[:8],
        "question_form": QuestionForm(),
        "ai_configured": ai.is_configured(),
    })


@membership_required
def document_upload(request):
    form = DocumentUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        document = services.create_document(
            strata=request.strata,
            user=request.user,
            title=form.cleaned_data["title"],
            category=form.cleaned_data["category"],
            file=form.cleaned_data["file"],
        )
        messages.success(request, f"Uploaded {document.title}. The summary will appear here shortly.")
        return redirect("documents:detail", pk=document.pk)
    return render(request, "documents/upload.html", {"form": form})


@membership_required
def document_detail(request, pk):
    document = _get_document(request, pk)
    return render(request, "documents/detail.html", {
        "document": document,
        "can_delete": request.membership.is_manager or document.uploaded_by_id == request.user.id,
    })


@membership_required
def document_summary(request, pk):
    """HTMX partial: polls while the summary is being generated."""
    return render(request, "documents/partials/summary.html", {"document": _get_document(request, pk)})


@membership_required
def document_file(request, pk):
    document = _get_document(request, pk)
    return FileResponse(document.file.open("rb"), content_type="application/pdf", filename=f"{document.title}.pdf")


@membership_required
@require_POST
def document_retry_summary(request, pk):
    document = _get_document(request, pk)
    document.summary_status = Document.SummaryStatus.PENDING
    document.save(update_fields=["summary_status", "updated_at"])
    services.queue_summary(document)
    return redirect("documents:detail", pk=pk)


@membership_required
@require_POST
def document_delete(request, pk):
    document = _get_document(request, pk)
    if not (request.membership.is_manager or document.uploaded_by_id == request.user.id):
        messages.error(request, "Only the uploader or the strata manager can delete this document.")
        return redirect("documents:detail", pk=pk)
    title = document.title
    services.delete_document(document)
    messages.success(request, f"Deleted {title}.")
    return redirect("documents:library")


@membership_required
@require_POST
def ask_documents(request):
    form = QuestionForm(request.POST)
    context = {"question_form": form}
    if form.is_valid():
        try:
            context["question"] = services.ask_question(request.strata, request.user, form.cleaned_data["question"])
        except ai.AIError as exc:
            context["error"] = str(exc)
    else:
        context["error"] = "Type a question first."

    if request.headers.get("HX-Request"):
        return render(request, "documents/partials/answer.html", context)
    if "question" in context:
        return redirect("documents:question", pk=context["question"].pk)
    messages.error(request, context["error"])
    return redirect("documents:library")


@membership_required
def question_detail(request, pk):
    question = get_object_or_404(DocumentQuestion, pk=pk, strata=request.strata)
    return render(request, "documents/question.html", {"question": question})
