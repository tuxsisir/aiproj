from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from .models import UserSubscription

def subscription_required(view_func):
    """
    Decorator for views that checks that the user has an active subscription.
    If not, redirects them to the checkout or pricing page.
    Assumes the user is already authenticated (@login_required should be used before this).
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('account_login')
            
        if hasattr(request.user, 'subscription') and request.user.subscription.is_active:
            return view_func(request, *args, **kwargs)
            
        messages.warning(request, "This feature requires an active subscription.")
        # Currently redirecting to dashboard. You could redirect to a specific pricing page.
        return redirect('dashboard')
        
    return _wrapped_view
