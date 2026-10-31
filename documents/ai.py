"""
The only module that talks to Claude. Everything here takes plain data and returns plain data,
so services and views can be tested with this module mocked.
"""
import anthropic
from pydantic import BaseModel

from core import ai as core_ai
from core.ai import BETAS, MODEL, AIError, is_configured  # noqa: F401  (re-exported for callers)


class SummaryPoint(BaseModel):
    text: str
    pages: list[int]


class SummaryTopic(BaseModel):
    name: str
    points: list[SummaryPoint]


class DocumentSummary(BaseModel):
    overview: str
    topics: list[SummaryTopic]
    key_numbers: list[SummaryPoint]


SUMMARY_SYSTEM = """You help strata council members and strata managers in British Columbia understand their \
building's documents (bylaws, rules, minutes, insurance, financial statements).

Summarize the attached document so a busy council member can find any rule in seconds:
- overview: 2-3 plain-language sentences on what the document is and covers.
- topics: group the content by everyday topic, using short familiar names such as Parking, Pets, Rentals, \
Short-term Rentals, Noise & Nuisance, Smoking, Renovations & Alterations, Moving In/Out, Garbage & Recycling, \
Common Property, Balconies & Patios, Storage, Strata Fees, Fines & Enforcement, Council & Meetings, Insurance. \
Only include topics the document actually covers. Each point is one concrete rule or fact, written plainly.
- key_numbers: specific amounts, limits and deadlines (fine amounts, number of pets, quiet hours, notice periods).
- pages: the 1-based page number(s) of the PDF file where each point appears (count PDF pages from the first \
page of the file, not the printed page labels).

Only state what the document says. Do not add legal advice or rules from elsewhere."""

ANSWER_SYSTEM = """You answer questions from strata council members and strata managers in British Columbia \
using only their building's documents, which are attached.

Answer directly and briefly, in plain language. Quote the relevant rule where it helps. If documents \
conflict (for example a newer bylaw amendment), say so and prefer the most recent one. If the documents \
don't answer the question, say that clearly instead of guessing. Do not give legal advice."""


def _client():
    return core_ai.client()


def upload_pdf(filename, fileobj):
    """Upload a PDF to the Claude Files API once; returns its file id."""
    try:
        uploaded = _client().files.upload(file=(filename, fileobj, "application/pdf"))
    except anthropic.APIError as exc:
        raise AIError(f"Couldn't upload the document to the AI service: {exc.message}") from exc
    return uploaded.id


def delete_file(file_id):
    try:
        _client().files.delete(file_id)
    except (anthropic.APIError, AIError):
        pass  # Best effort: an orphaned file only costs storage.


def summarize(file_id, title):
    """Return a DocumentSummary as a dict."""
    try:
        response = _client().beta.messages.parse(
            model=MODEL,
            max_tokens=16000,
            betas=BETAS,
            fallbacks="default",
            system=SUMMARY_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "file", "file_id": file_id}, "title": title},
                    {"type": "text", "text": f"Summarize \"{title}\"."},
                ],
            }],
            output_format=DocumentSummary,
        )
    except anthropic.APIError as exc:
        raise AIError(f"The AI service couldn't summarize this document: {exc.message}") from exc

    core_ai.raise_for_stop_reason(response)
    if response.parsed_output is None:
        raise AIError("The AI service returned an unreadable summary. Try again.")
    return response.parsed_output.model_dump()


def answer(question, documents):
    """
    Answer `question` from `documents` ([{"id", "title", "file_id"}], stable order for caching).
    Returns (segments, usage) where segments is [{"text", "citations": [{"document_id", "title", "page", "quote"}]}].
    """
    if not documents:
        raise AIError("Upload a document first.")

    doc_blocks = [
        {
            "type": "document",
            "source": {"type": "file", "file_id": d["file_id"]},
            "title": d["title"],
            "citations": {"enabled": True},
        }
        for d in documents
    ]
    # Cache the system prompt + documents so follow-up questions only pay for the question.
    doc_blocks[-1]["cache_control"] = {"type": "ephemeral"}

    try:
        with _client().beta.messages.stream(
            model=MODEL,
            max_tokens=16000,
            betas=BETAS,
            fallbacks="default",
            system=ANSWER_SYSTEM,
            messages=[{"role": "user", "content": [*doc_blocks, {"type": "text", "text": question}]}],
        ) as stream:
            response = stream.get_final_message()
    except anthropic.APIError as exc:
        raise AIError(f"The AI service couldn't answer right now: {exc.message}") from exc

    core_ai.raise_for_stop_reason(response)

    segments = []
    for block in response.content:
        if block.type != "text":
            continue  # Skip thinking blocks and fallback markers.
        citations = []
        for c in block.citations or []:
            if getattr(c, "type", "") != "page_location":
                continue
            doc = documents[c.document_index]
            citations.append({
                "document_id": str(doc["id"]),
                "title": doc["title"],
                "page": c.start_page_number,
                "quote": c.cited_text,
            })
        segments.append({"text": block.text, "citations": citations})

    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cache_read_input_tokens": response.usage.cache_read_input_tokens or 0,
        "cache_creation_input_tokens": response.usage.cache_creation_input_tokens or 0,
        "model": response.model,
    }
    return segments, usage
