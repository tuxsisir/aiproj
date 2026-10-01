from django.contrib.contenttypes.models import ContentType
from core.models import AuditLog

def record_audit_log(instance, actor, action=None, request=None, custom_summary=None):
    dirty = getattr(instance, 'get_dirty_fields', lambda: {})()
    is_new = instance._state.adding

    if is_new:
        chosen_action = action or AuditLog.Action.CREATE
        summary = custom_summary or f"Created {instance.__class__.__name__}"
    elif dirty:
        chosen_action = action or AuditLog.Action.UPDATE
        fields_str = ", ".join(dirty.keys())
        summary = custom_summary or f"Updated {fields_str}"
    else:
        return None  # Nothing changed

    ip = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR')

    log = AuditLog.objects.create(
        content_type=ContentType.objects.get_for_model(instance),
        object_id=str(instance.pk),
        actor=actor if actor and actor.is_authenticated else None,
        actor_email=actor.email if actor and actor.is_authenticated else "System",
        actor_ip=ip,
        action=chosen_action,
        summary=summary,
        changes=dirty,
    )
    
    if hasattr(instance, 'reset_initial_state'):
        instance.reset_initial_state()
        
    return log
