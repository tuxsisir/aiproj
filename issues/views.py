from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inbox.models import InboundEmail
from stratas.decorators import membership_required
from . import services
from .forms import IssueFilterForm, IssueForm, IssueUpdateForm
from .models import Issue

CATEGORY_FOR_EMAIL = {
    "Maintenance & Repairs": Issue.Category.MAINTENANCE,
    "Bylaw Complaint": Issue.Category.OTHER,
    "Owner Request": Issue.Category.OTHER,
}
PRIORITY_FOR_EMAIL = {"low": Issue.Priority.LOW, "normal": Issue.Priority.NORMAL,
                      "high": Issue.Priority.HIGH, "urgent": Issue.Priority.URGENT}


@membership_required
def issue_list(request):
    filters = IssueFilterForm(request.GET)
    show = filters.is_valid() and filters.cleaned_data.get("show") or "open"
    issues = request.strata.issues.select_related("assigned_to", "raised_by")
    shown = {
        "open": issues.open(),
        "mine": issues.open().filter(assigned_to=request.user),
        "closed": issues.closed(),
        "all": issues,
    }[show]
    counts = issues.aggregate(
        open=Count("id", filter=~Q(status__in=Issue.CLOSED)),
        mine=Count("id", filter=~Q(status__in=Issue.CLOSED) & Q(assigned_to=request.user)),
        closed=Count("id", filter=Q(status__in=Issue.CLOSED)),
        unanswered=Count("id", filter=Q(status=Issue.Status.OPEN)),
    )
    return render(request, "issues/list.html", {"issues": shown, "show": show, "counts": counts})


@membership_required
def issue_create(request):
    email = _source_email(request)
    initial = _from_email(email) if email else None
    form = IssueForm(request.POST or None, strata=request.strata, initial=initial)
    if request.method == "POST" and form.is_valid():
        issue = services.raise_issue(request.strata, request.user, request=request, source_email=email,
                                     **form.cleaned_data)
        messages.success(request, f"Issue raised: {issue.title}")
        return redirect("issues:detail", pk=issue.pk)
    return render(request, "issues/form.html", {"form": form, "source_email": email})


@membership_required
def issue_detail(request, pk):
    issue = _get_issue(request, pk)
    return render(request, "issues/detail.html", {
        "issue": issue,
        "updates": issue.updates.select_related("author"),
        "form": IssueUpdateForm(issue=issue),
    })


@membership_required
@require_POST
def issue_update(request, pk):
    issue = _get_issue(request, pk)
    form = IssueUpdateForm(request.POST, issue=issue)
    if form.is_valid():
        services.update_issue(issue, request.user, form.cleaned_data, request=request)
        messages.success(request, "Issue updated.")
        return redirect("issues:detail", pk=issue.pk)
    return render(request, "issues/detail.html", {
        "issue": issue,
        "updates": issue.updates.select_related("author"),
        "form": form,
    }, status=400)


def _get_issue(request, pk):
    return get_object_or_404(Issue.objects.select_related("assigned_to", "raised_by", "source_email"),
                             pk=pk, strata=request.strata)


def _source_email(request):
    """?from_email=<id> (or the hidden POST field): a forwarded email of this building to raise an issue from."""
    email_id = request.POST.get("from_email") or request.GET.get("from_email")
    if not email_id:
        return None
    try:
        return InboundEmail.objects.filter(pk=email_id, strata=request.strata).first()
    except (ValidationError, ValueError):  # not a valid UUID
        return None


def _from_email(email):
    summary = email.summary or {}
    return {
        "title": summary.get("title") or email.subject,
        "description": summary.get("summary", ""),
        "category": CATEGORY_FOR_EMAIL.get(summary.get("category"), Issue.Category.MAINTENANCE),
        "priority": PRIORITY_FOR_EMAIL.get(summary.get("urgency"), Issue.Priority.NORMAL),
    }
