"""Issue lifecycle: raise, move along, close. Every change lands on the timeline and the audit log."""
from django.utils import timezone

from core import emails
from core.models import AuditLog
from core.services import record_audit_log
from stratas.services import member_emails
from .models import Issue, IssueUpdate


def raise_issue(strata, user, request=None, source_email=None, **fields):
    issue = Issue.objects.create(strata=strata, raised_by=user, source_email=source_email, **fields)
    IssueUpdate.objects.create(issue=issue, author=user, kind=IssueUpdate.Kind.CREATED,
                               body=f"Raised by {_name(user)}" + (" from a forwarded email" if source_email else ""))
    record_audit_log(issue, user, action=AuditLog.Action.CREATE, request=request)

    others = [e for e in member_emails(strata) if e != user.email]
    emails.send("issue_raised", others, {"issue": issue})
    if issue.assigned_to and issue.assigned_to != user:
        emails.send("issue_assigned", [issue.assigned_to.email], {"issue": issue, "assigned_by": user})
    return issue


def update_issue(issue, user, data, request=None):
    """Apply an IssueUpdateForm's cleaned data. Saves first, then notifies."""
    now = timezone.now()
    entries = []
    old_status, old_assignee = issue.status, issue.assigned_to

    if data["status"] != old_status:
        issue.status = data["status"]
        if old_status == Issue.Status.OPEN and not issue.acknowledged_at:
            issue.acknowledged_at = now
        if issue.status in Issue.CLOSED:
            issue.resolved_at = now
            issue.outcome = data["outcome"].strip() or issue.outcome  # RESOLVED → CLOSED keeps the outcome
        else:
            issue.resolved_at = None
        body = f"{Issue.Status(old_status).label} → {issue.get_status_display()}"
        if issue.status in Issue.CLOSED:
            body += f". Outcome: {issue.outcome}"
        entries.append((IssueUpdate.Kind.STATUS, body))

    if data.get("assigned_to") != old_assignee:
        issue.assigned_to = data.get("assigned_to")
        if issue.status == Issue.Status.OPEN and issue.assigned_to:
            issue.status, issue.acknowledged_at = Issue.Status.ACKNOWLEDGED, issue.acknowledged_at or now
        entries.append((IssueUpdate.Kind.ASSIGNED,
                        f"Owner: {_name(issue.assigned_to) if issue.assigned_to else 'nobody'}"))

    details = []
    if data.get("due_date") != issue.due_date:
        issue.due_date = data.get("due_date")
        details.append(f"fix by {issue.due_date:%b} {issue.due_date.day}, {issue.due_date.year}" if issue.due_date else "no fix-by date")
    if data.get("vendor", "") != issue.vendor:
        issue.vendor = data.get("vendor", "")
        details.append(f"vendor {issue.vendor}" if issue.vendor else "no vendor")
    if details:
        entries.append((IssueUpdate.Kind.DETAILS, "Set " + ", ".join(details)))

    if data.get("comment", "").strip():
        entries.append((IssueUpdate.Kind.COMMENT, data["comment"].strip()))

    issue.last_activity_at = now
    issue.save()
    for kind, body in entries:
        IssueUpdate.objects.create(issue=issue, author=user, kind=kind, body=body)
    record_audit_log(issue, user, action=AuditLog.Action.UPDATE, request=request)
    issue.reset_initial_state()

    if issue.assigned_to and issue.assigned_to != old_assignee and issue.assigned_to != user:
        emails.send("issue_assigned", [issue.assigned_to.email], {"issue": issue, "assigned_by": user})
    return issue


def _name(user):
    return (user.get_full_name() or user.email) if user else "someone"
