import shutil
import tempfile
from types import SimpleNamespace
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from core.testing import make_membership, make_strata, make_user
from stratas.models import Membership
from . import ai, services
from .models import Document, DocumentQuestion

PDF_BYTES = b"%PDF-1.4\n%fake test pdf\n"
SUMMARY = {
    "overview": "Consolidated bylaws.",
    "topics": [{"name": "Parking", "points": [{"text": "Visitors may park 24 hours max.", "pages": [4]}]}],
    "key_numbers": [{"text": "Fine up to $200 per contravention.", "pages": [12]}],
}
ANSWER = [
    {"text": "Visitor parking is limited to 24 hours.", "citations": []},
]

MEDIA_ROOT = tempfile.mkdtemp()


def pdf(name="bylaws.pdf", content=PDF_BYTES):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


@override_settings(MEDIA_ROOT=MEDIA_ROOT, ANTHROPIC_API_KEY="test-key")
class DocumentTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.strata = make_strata()
        self.member = make_membership(make_user(), self.strata)
        self.client.force_login(self.member.user)

    def make_document(self, strata=None, title="Bylaws", **extra):
        return Document.objects.create(
            strata=strata or self.strata, title=title, file=pdf(), uploaded_by=self.member.user, **extra
        )


class UploadTests(DocumentTestCase):
    def test_upload_creates_document_and_queues_summary(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            response = self.client.post(reverse("documents:upload"), {
                "title": "Bylaws 2024", "category": Document.Category.BYLAWS, "file": pdf(),
            })
        document = Document.objects.get()
        self.assertRedirects(response, reverse("documents:detail", args=[document.pk]))
        self.assertEqual((document.strata, document.uploaded_by), (self.strata, self.member.user))
        self.assertEqual(len(callbacks), 1)

    def test_rejects_non_pdf(self):
        self.client.post(reverse("documents:upload"), {
            "title": "x", "category": Document.Category.OTHER, "file": pdf("notes.pdf", b"hello"),
        })
        self.assertFalse(Document.objects.exists())

    @override_settings(ANTHROPIC_API_KEY="")
    def test_upload_without_ai_key_marks_summary_failed(self):
        self.client.post(reverse("documents:upload"), {
            "title": "x", "category": Document.Category.OTHER, "file": pdf(),
        })
        document = Document.objects.get()
        self.assertEqual(document.summary_status, Document.SummaryStatus.FAILED)
        self.assertIn("ANTHROPIC_API_KEY", document.summary_error)


class SummarizeTests(DocumentTestCase):
    @mock.patch.object(ai, "summarize", return_value=SUMMARY)
    @mock.patch.object(ai, "upload_pdf", return_value="file_123")
    def test_summary_stored_and_file_uploaded_once(self, upload_pdf, summarize):
        document = self.make_document()
        services.summarize_document(document)
        services.summarize_document(document)
        document.refresh_from_db()
        self.assertEqual(document.summary_status, Document.SummaryStatus.READY)
        self.assertEqual(document.summary, SUMMARY)
        self.assertEqual(document.claude_file_id, "file_123")
        upload_pdf.assert_called_once()
        summarize.assert_called_with("file_123", "Bylaws")

    @mock.patch.object(ai, "summarize", side_effect=ai.AIError("Service unavailable"))
    @mock.patch.object(ai, "upload_pdf", return_value="file_123")
    def test_ai_failure_is_recorded(self, upload_pdf, summarize):
        document = services.summarize_document(self.make_document())
        self.assertEqual((document.summary_status, document.summary_error), (Document.SummaryStatus.FAILED, "Service unavailable"))

    def test_detail_renders_summary_with_page_links(self):
        document = self.make_document(summary=SUMMARY, summary_status=Document.SummaryStatus.READY)
        response = self.client.get(reverse("documents:detail", args=[document.pk]))
        self.assertContains(response, "Visitors may park 24 hours max.")
        self.assertContains(response, f"{reverse('documents:file', args=[document.pk])}#page=4")

    def test_pending_summary_polls(self):
        document = self.make_document()
        response = self.client.get(reverse("documents:summary", args=[document.pk]))
        self.assertContains(response, 'hx-trigger="every 3s"')

    def test_retry_requeues(self):
        document = self.make_document(summary_status=Document.SummaryStatus.FAILED)
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.client.post(reverse("documents:retry", args=[document.pk]))
        document.refresh_from_db()
        self.assertEqual(document.summary_status, Document.SummaryStatus.PENDING)
        self.assertEqual(len(callbacks), 1)


class AccessTests(DocumentTestCase):
    def test_file_is_served_to_members(self):
        document = self.make_document()
        response = self.client.get(reverse("documents:file", args=[document.pk]))
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(b"".join(response.streaming_content), PDF_BYTES)

    def test_other_buildings_documents_are_hidden(self):
        document = self.make_document(strata=make_strata(), title="Neighbour Secret Minutes")
        for name in ("detail", "file", "summary"):
            self.assertEqual(self.client.get(reverse(f"documents:{name}", args=[document.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("documents:library")), "Neighbour Secret Minutes")

    def test_pending_member_cannot_open_library(self):
        user = make_user()
        make_membership(user, self.strata, status=Membership.Status.PENDING)
        self.client.force_login(user)
        self.assertRedirects(self.client.get(reverse("documents:library")), reverse("membership_pending"))

    @mock.patch.object(ai, "delete_file")
    def test_only_uploader_or_manager_can_delete(self, delete_file):
        document = self.make_document(claude_file_id="file_9")
        other = make_membership(make_user(), self.strata)
        self.client.force_login(other.user)
        self.client.post(reverse("documents:delete", args=[document.pk]))
        self.assertTrue(Document.objects.exists())

        manager = make_membership(make_user(), self.strata, role=Membership.Role.MANAGER)
        self.client.force_login(manager.user)
        self.client.post(reverse("documents:delete", args=[document.pk]))
        self.assertFalse(Document.objects.exists())
        delete_file.assert_called_once_with("file_9")


class AskTests(DocumentTestCase):
    def setUp(self):
        super().setUp()
        self.first = self.make_document(claude_file_id="file_1")
        self.second = self.make_document(claude_file_id="file_2", title="Rules")

    @mock.patch.object(ai, "answer", return_value=(ANSWER, {"input_tokens": 10}))
    def test_htmx_question_returns_answer_and_is_saved(self, answer):
        response = self.client.post(
            reverse("documents:ask"), {"question": "Visitor parking?"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "Visitor parking is limited to 24 hours.")
        question = DocumentQuestion.objects.get()
        self.assertEqual((question.asked_by, question.strata), (self.member.user, self.strata))
        docs = answer.call_args.args[1]
        self.assertEqual([d["file_id"] for d in docs], ["file_1", "file_2"])

    @mock.patch.object(ai, "answer", return_value=(ANSWER, {}))
    def test_plain_post_redirects_to_saved_question(self, answer):
        response = self.client.post(reverse("documents:ask"), {"question": "Visitor parking?"})
        self.assertRedirects(response, reverse("documents:question", args=[DocumentQuestion.objects.get().pk]))

    @mock.patch.object(ai, "answer", side_effect=ai.AIError("The AI service couldn't answer right now."))
    def test_ai_error_is_shown(self, answer):
        response = self.client.post(reverse("documents:ask"), {"question": "x"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "couldn&#x27;t answer right now")
        self.assertFalse(DocumentQuestion.objects.exists())

    def test_questions_from_other_buildings_are_hidden(self):
        question = DocumentQuestion.objects.create(strata=make_strata(), question="secret")
        self.assertEqual(self.client.get(reverse("documents:question", args=[question.pk])).status_code, 404)


@override_settings(ANTHROPIC_API_KEY="test-key")
class AnswerParsingTests(TestCase):
    """ai.answer maps Claude's page citations back to our documents."""

    def fake_client(self, content, stop_reason="end_turn"):
        response = SimpleNamespace(
            content=content,
            stop_reason=stop_reason,
            model=ai.MODEL,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=80, cache_creation_input_tokens=0),
        )
        stream = mock.MagicMock()
        stream.__enter__.return_value.get_final_message.return_value = response
        client = mock.MagicMock()
        client.beta.messages.stream.return_value = stream
        return client

    def test_citations_point_to_the_right_document_and_page(self):
        content = [
            SimpleNamespace(type="thinking", thinking=""),
            SimpleNamespace(type="text", text="Visitors get 24 hours", citations=[
                SimpleNamespace(type="page_location", document_index=1, start_page_number=4, cited_text="24 hours"),
            ]),
        ]
        docs = [{"id": "a", "title": "Bylaws", "file_id": "f1"}, {"id": "b", "title": "Rules", "file_id": "f2"}]
        client = self.fake_client(content)
        with mock.patch.object(ai, "_client", return_value=client):
            segments, usage = ai.answer("parking?", docs)

        self.assertEqual(segments, [{"text": "Visitors get 24 hours", "citations": [
            {"document_id": "b", "title": "Rules", "page": 4, "quote": "24 hours"},
        ]}])
        self.assertEqual(usage["cache_read_input_tokens"], 80)
        sent = client.beta.messages.stream.call_args.kwargs
        self.assertEqual(sent["model"], "claude-opus-5-5")
        blocks = sent["messages"][0]["content"]
        self.assertIn("cache_control", blocks[1])
        self.assertEqual(blocks[-1], {"type": "text", "text": "parking?"})

    def test_refusal_raises_user_facing_error(self):
        client = self.fake_client([], stop_reason="refusal")
        with mock.patch.object(ai, "_client", return_value=client), self.assertRaises(ai.AIError):
            ai.answer("x", [{"id": "a", "title": "t", "file_id": "f"}])

    @override_settings(ANTHROPIC_API_KEY="")
    def test_missing_key_raises(self):
        with self.assertRaises(ai.AIError):
            ai.answer("x", [{"id": "a", "title": "t", "file_id": "f"}])
