from core.models import AuditLog
from core.services import record_audit_log
from .models import KeyDate


def create_key_date(strata, user, request=None, **fields):
    key_date = KeyDate.objects.create(strata=strata, created_by=user, **fields)
    record_audit_log(key_date, user, action=AuditLog.Action.CREATE, request=request)
    return key_date


def update_key_date(key_date, user, request=None):
    """Save and audit the from/to of what changed; nothing is logged when nothing changed."""
    if not key_date.get_dirty_fields():
        return
    key_date.save()
    record_audit_log(key_date, user, action=AuditLog.Action.UPDATE, request=request)
    key_date.reset_initial_state()


def delete_key_date(key_date, user, request=None):
    summary = (
        f"Deleted key date {key_date.title} ({key_date.date}, {key_date.get_category_display()}"
        f"{', yearly' if key_date.repeats_yearly else ''}){': ' + key_date.note if key_date.note else ''}"
    )
    record_audit_log(key_date, user, action=AuditLog.Action.DELETE, request=request, custom_summary=summary[:255])
    key_date.delete()
