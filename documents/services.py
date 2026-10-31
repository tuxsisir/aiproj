"""
Document lifecycle: upload -> summarize (background) -> ask questions across documents.
All Claude calls go through documents.ai.
"""
import logging

from django.utils import timezone

from core import emails
from core.background import run_after_commit
from . import ai
from .models import Document, DocumentQuestion

logger = logging.getLogger(__name__)


def create_document(strata, user, title, category, file):
    document = Document.objects.create(
        strata=strata, uploaded_by=user, title=title, category=category, file=file
    )
    queue_summary(document)
    return document


def queue_summary(document):
    """Summarize after the upload commits, without blocking the request."""
    if not ai.is_configured():
        _fail(document, "AI isn't set up yet. Add ANTHROPIC_API_KEY, then retry.")
        return
    run_after_commit(_summarize_by_pk, document.pk)


def _summarize_by_pk(document_pk):
    summarize_document(Document.objects.get(pk=document_pk))


def summarize_document(document):
    """Upload to Claude if needed, then store the structured summary. Never raises."""
    document.summary_status = Document.SummaryStatus.PROCESSING
    document.summary_error = ""
    document.save(update_fields=["summary_status", "summary_error", "updated_at"])
    try:
        ensure_uploaded(document)
        document.summary = ai.summarize(document.claude_file_id, document.title)
    except ai.AIError as exc:
        _fail(document, str(exc))
        return document
    except Exception:
        logger.exception("Summarizing document %s failed", document.pk)
        _fail(document, "Something went wrong while summarizing. Try again.")
        return document

    document.summary_status = Document.SummaryStatus.READY
    document.summarized_at = timezone.now()
    document.save(update_fields=["summary", "summary_status", "summarized_at", "updated_at"])
    if document.uploaded_by:
        emails.send("document_summarized", [document.uploaded_by.email], {"document": document})
    return document


def ensure_uploaded(document):
    if not document.claude_file_id:
        with document.file.open("rb") as fh:
            document.claude_file_id = ai.upload_pdf(f"{document.title}.pdf", fh)
        document.save(update_fields=["claude_file_id", "updated_at"])
    return document.claude_file_id


def ask_question(strata, user, question):
    """Answer from all of the building's documents. Raises ai.AIError with a user-facing message."""
    documents = list(strata.documents.order_by("created_at"))
    for document in documents:
        ensure_uploaded(document)
    segments, usage = ai.answer(
        question,
        [{"id": d.id, "title": d.title, "file_id": d.claude_file_id} for d in documents],
    )
    return DocumentQuestion.objects.create(
        strata=strata, asked_by=user, question=question, answer=segments, usage=usage
    )


def delete_document(document):
    if document.claude_file_id:
        ai.delete_file(document.claude_file_id)
    document.file.delete(save=False)
    document.delete()


def _fail(document, message):
    document.summary_status = Document.SummaryStatus.FAILED
    document.summary_error = message[:255]
    document.save(update_fields=["summary_status", "summary_error", "updated_at"])
