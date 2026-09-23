from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
import re
from .models import Membership

class ActiveStrataMiddleware(MiddlewareMixin):
    """
    Inspects each authenticated request and resolves:
      1. request.strata -> The active StrataPlan instance (or None)
      2. request.membership -> The active Membership linking request.user to request.strata
    """
    def process_request(self, request):
        if not request.user.is_authenticated:
            request.strata = None
            request.membership = None
            return

        active_id = request.session.get("active_strata_id")
        membership = None

        if active_id:
            membership = Membership.objects.filter(
                user=request.user, 
                strata_id=active_id, 
                is_active=True
            ).select_related("strata").first()

        # Fallback to the first available active membership if session key is absent/invalid
        if not membership:
            membership = Membership.objects.filter(
                user=request.user, 
                is_active=True
            ).select_related("strata").first()

        if membership:
            request.strata = membership.strata
            request.membership = membership
            request.session["active_strata_id"] = str(membership.strata.id)
        else:
            request.strata = None
            request.membership = None

        # Gating Logic
        path = request.path_info
        
        exempt_paths = [
            r'^/static/',
            r'^/media/',
            r'^/accounts/',
            r'^/profile/',
            r'^/stratas/onboarding/',
            r'^/dockets/actions/',
            r'^/dockets/respond/',
            r'^/payments/webhook/',
            r'^/admin/',
            r'^/__debug__/',
            r'^/$'
        ]
        
        is_exempt = any(re.match(pattern, path) for pattern in exempt_paths)
        
        if not is_exempt:
            if not membership:
                return redirect('onboarding')
        
        if path == '/stratas/onboarding/' and membership:
            if membership.role != Membership.Role.STRATA_MANAGER:
                return redirect('dashboard')
