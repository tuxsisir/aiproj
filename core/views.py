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


@login_required
def create_checkout_session(request):
    """Create a Stripe checkout session for a subscription or payment."""
    if request.method == "POST":
        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[
                    {
                        # Provide the exact Price ID (for example, pr_1234) of the product you want to sell
                        'price': 'price_1234567890', # Replace with your real price ID
                        'quantity': 1,
                    },
                ],
                mode='subscription', # or 'payment'
                success_url=request.build_absolute_uri('/dashboard/') + '?success=true',
                cancel_url=request.build_absolute_uri('/dashboard/') + '?canceled=true',
                client_reference_id=str(request.user.id),
                customer_email=request.user.email,
            )
            return redirect(checkout_session.url, code=303)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return redirect('dashboard')


@csrf_exempt
def stripe_webhook(request):
    """Handle Stripe webhooks to update Subscription/Payment status."""
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        # Invalid payload
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        return HttpResponse(status=400)

    # Handle the event
    if event.type == 'checkout.session.completed':
        session = event.data.object
        # client_reference_id contains the user ID
        # Here you would create or update the Subscription model
        print("Payment was successful!")
        
    elif event.type == 'customer.subscription.updated':
        subscription = event.data.object
        # Update your Subscription model
        
    elif event.type == 'customer.subscription.deleted':
        subscription = event.data.object
        # Mark subscription as canceled
        
    return HttpResponse(status=200)
