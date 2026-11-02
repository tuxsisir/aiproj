import json
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.views.decorators.clickjacking import xframe_options_sameorigin

from core import emails
from core.email_previews import sample_context

stripe.api_key = settings.STRIPE_SECRET_KEY


def landing_page(request):
    """Public landing page."""
    return render(request, "landing.html")


from core import overview
from stratas.decorators import membership_required


@membership_required
def dashboard(request):
    """Overview: what needs this member now, each pillar at a glance, what's coming, what just happened."""
    membership = request.membership
    needs = overview.needs_you(membership)
    return render(request, "dashboard.html", {
        "needs": needs,
        "on_you": sum(n.on_you for n in needs),
        "pillars": overview.pillars(request.strata),
        "recent": overview.recent_activity(request.strata),
        "portfolio": overview.portfolio(request.user) if membership.is_manager else None,
        "hour": timezone.localtime().hour,
    })


@login_required
def profile_edit(request):
    """Edit user profile and avatar."""
    if request.method == "POST":
        user = request.user
        
        # Handle avatar upload
        if 'avatar' in request.FILES:
            user.avatar = request.FILES['avatar']
            
        # Handle other info
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        if not first_name or not last_name:
            messages.error(request, "First name and last name are required.")
            return redirect('profile_edit')
            
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('profile_edit')
        
    return render(request, "profile_edit.html")






def _render_email_or_404(key):
    if key not in emails.EMAILS:
        raise Http404("Unknown email")
    return emails.render(key, sample_context())


@staff_member_required
def email_preview_list(request):
    context = sample_context()
    rows = [
        {"key": key, "spec": spec, "subject": emails.render(key, context)[0]}
        for key, spec in emails.EMAILS.items()
    ]
    return render(request, "emails/preview_list.html", {"rows": rows, "title": "Email previews"})


@staff_member_required
def email_preview(request, key):
    subject, _, _ = _render_email_or_404(key)
    return render(request, "emails/preview.html", {
        "key": key, "spec": emails.EMAILS[key], "subject": subject, "title": f"Email preview: {key}",
    })


@staff_member_required
@xframe_options_sameorigin
def email_preview_body(request, key, fmt):
    _, text, html = _render_email_or_404(key)
    if fmt == "text":
        return HttpResponse(text, content_type="text/plain; charset=utf-8")
    return HttpResponse(html)
