"""Shared Claude plumbing. Feature modules (documents.ai, inbox.ai) hold their own prompts and schemas."""
import anthropic
from django.conf import settings

MODEL = "claude-opus-5-5"
# Server-side fallback: if the model declines a request, the API retries on a suitable model.
BETAS = ["server-side-fallback-2026-07-01"]


class AIError(Exception):
    """User-presentable failure (not configured, refused, too large, API down)."""


def is_configured():
    return bool(settings.ANTHROPIC_API_KEY)


def client():
    if not is_configured():
        raise AIError("AI isn't set up yet (ANTHROPIC_API_KEY is missing).")
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def raise_for_stop_reason(response):
    if response.stop_reason == "refusal":
        raise AIError("The AI service declined this request.")
    if response.stop_reason == "max_tokens":
        raise AIError("The response was cut off. Try something narrower.")
