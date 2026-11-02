from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core import ai as core_ai
from stratas.decorators import membership_required
from . import services
from .models import InboundEmail


def _get_email(request, pk):
    return get_object_or_404(InboundEmail, pk=pk, strata=request.strata)


@membership_required
def inbox_home(request):
    return render(request, "inbox/home.html", {
        "inbox": services.get_or_create_inbox(request.strata),
        "emails": request.strata.inbound_emails.select_related("forwarded_by")[:50],
        "ai_configured": core_ai.is_configured(),
    })


@membership_required
def email_detail(request, pk):
    email = _get_email(request, pk)
    return render(request, "inbox/detail.html", {"email": email, "issue": email.issues.first()})


@membership_required
def email_summary(request, pk):
    """HTMX partial: polls while the summary is being generated."""
    return render(request, "inbox/partials/summary.html", {"email": _get_email(request, pk)})


@membership_required
@require_POST
def email_retry(request, pk):
    email = _get_email(request, pk)
    email.status = InboundEmail.Status.PENDING
    email.save(update_fields=["status", "updated_at"])
    services.queue_summary(email)
    return redirect("inbox:detail", pk=pk)
