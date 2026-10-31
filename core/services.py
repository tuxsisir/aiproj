from django.contrib.contenttypes.models import ContentType
from core.models import AuditLog


def record_audit_log(instance, actor, action=None, request=None, custom_summary=None):
    """
    Write an immutable audit entry for `instance`.

    With an explicit `action` the entry is always written (field diffs included when there are any).
    Without one, the action is inferred: CREATE for an unsaved instance, UPDATE when tracked fields
    changed, otherwise nothing is written and None is returned.
    """
    dirty = getattr(instance, 'get_dirty_fields', lambda: {})()

    if action is None:
        if instance._state.adding:
            action = AuditLog.Action.CREATE
        elif dirty:
            action = AuditLog.Action.UPDATE
        else:
            return None

    if custom_summary:
        summary = custom_summary
    elif action == AuditLog.Action.UPDATE and dirty:
        summary = f"Updated {', '.join(dirty.keys())}"
    else:
        summary = f"{AuditLog.Action(action).label} {instance.__class__.__name__}"

    ip = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

    is_user = bool(actor and actor.is_authenticated)
    log = AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(instance),
        object_id=str(instance.pk),
        actor=actor if is_user else None,
        actor_email=actor.email if is_user else "",
        actor_ip=ip,
        action=action,
        summary=summary[:255],
        changes=dirty,
    )

    if hasattr(instance, 'reset_initial_state'):
        instance.reset_initial_state()

    return log
