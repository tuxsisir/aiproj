from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
import re
from .models import Membership

EXEMPT_PATHS = [
    r'^/static/',
    r'^/media/',
    r'^/accounts/',
    r'^/profile/',
    r'^/stratas/onboarding/',
    r'^/stratas/pending/',
    r'^/dockets/actions/',
    r'^/dockets/respond/',
    r'^/payments/webhooks/',
    r'^/anymail/',
    r'^/admin/',
    r'^/__debug__/',
    r'^/dev/',
    r'^/$'
]

class ActiveStrataMiddleware(MiddlewareMixin):
    """
    Inspects each authenticated request and resolves:
      1. request.strata -> The active StrataPlan instance (or None)
      2. request.membership -> The ACTIVE Membership linking request.user to request.strata
    Users without an active membership are sent to onboarding, or to the pending page
    while a membership request awaits approval. The platform admin (superuser) goes to Django admin.
    """
    def process_request(self, request):
        request.strata = None
        request.membership = None
        if not request.user.is_authenticated:
            return

        active = (
            Membership.objects.active().filter(user=request.user)
            .select_related("strata").order_by("joined_at")
        )
        active_id = request.session.get("active_strata_id")
        membership = None

        if active_id:
            membership = active.filter(strata_id=active_id).first()

        # Fallback to the first available active membership if session key is absent/invalid
        if not membership:
            membership = active.first()

        if membership:
            request.strata = membership.strata
            request.membership = membership
            request.session["active_strata_id"] = str(membership.strata.id)

        path = request.path_info
        if any(re.match(pattern, path) for pattern in EXEMPT_PATHS):
            return

        if not membership:
            if request.user.is_superuser:  # the platform admin works in Django admin, not a building
                return redirect('admin:index')
            if Membership.objects.pending().filter(user=request.user).exists():
                return redirect('membership_pending')
            return redirect('onboarding')
