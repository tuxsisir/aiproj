import json
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

stripe.api_key = settings.STRIPE_SECRET_KEY


def landing_page(request):
    """Public landing page."""
    return render(request, "landing.html")


@login_required
def dashboard(request):
    """Protected dashboard area."""
    return render(request, "dashboard.html")


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



