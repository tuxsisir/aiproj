from functools import wraps

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def membership_required(view_func):
    """Logged in with an active membership; request.strata / request.membership are then set."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not getattr(request, "membership", None):
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)
    return wrapper
