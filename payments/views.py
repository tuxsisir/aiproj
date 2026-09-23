import stripe
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
import datetime

from .models import UserSubscription

stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
def subscription_dashboard(request):
    """Render the billing and subscription management page."""
    return render(request, 'payments/subscription_dashboard.html')


@login_required
def create_checkout_session(request):
    """Create a Stripe checkout session for a subscription."""
    if request.method == "POST":
        try:
            # Note: We pass the user id so we can identify them in the webhook
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[
                    {
                        # Replace with your actual Stripe Price ID
                        'price': settings.STRIPE_PRICE_ID if hasattr(settings, 'STRIPE_PRICE_ID') else 'price_1234567890',
                        'quantity': 1,
                    },
                ],
                mode='subscription',
                success_url=request.build_absolute_uri('/dashboard/') + '?success=true',
                cancel_url=request.build_absolute_uri('/dashboard/') + '?canceled=true',
                client_reference_id=str(request.user.id),
                customer_email=request.user.email,
            )
            return redirect(checkout_session.url, code=303)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return redirect('dashboard')


@login_required
def customer_portal(request):
    """
    Redirects the user to the Stripe Customer Portal
    where they can update their card, view invoices, or cancel their subscription.
    """
    try:
        subscription = UserSubscription.objects.get(user=request.user)
        if not subscription.stripe_customer_id:
            return redirect('dashboard')
            
        session = stripe.billing_portal.Session.create(
            customer=subscription.stripe_customer_id,
            return_url=request.build_absolute_uri('/dashboard/'),
        )
        return redirect(session.url)
    except UserSubscription.DoesNotExist:
        return redirect('dashboard')
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def stripe_webhook(request):
    """Handle Stripe webhooks to update the local UserSubscription status."""
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

    # Handle the events
    if event.type == 'checkout.session.completed':
        session = event.data.object
        
        # client_reference_id is the user's UUID
        user_id = session.get('client_reference_id')
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        
        if user_id and customer_id and subscription_id:
            # Retrieve subscription to get status and period end
            stripe_sub = stripe.Subscription.retrieve(subscription_id)
            
            sub, created = UserSubscription.objects.get_or_create(user_id=user_id)
            sub.stripe_customer_id = customer_id
            sub.stripe_subscription_id = subscription_id
            sub.status = stripe_sub.status
            sub.current_period_end = timezone.make_aware(datetime.datetime.fromtimestamp(stripe_sub.current_period_end))
            sub.save()
            
    elif event.type in ['customer.subscription.updated', 'customer.subscription.deleted']:
        stripe_sub = event.data.object
        subscription_id = stripe_sub.id
        
        try:
            sub = UserSubscription.objects.get(stripe_subscription_id=subscription_id)
            sub.status = stripe_sub.status
            sub.current_period_end = timezone.make_aware(datetime.datetime.fromtimestamp(stripe_sub.current_period_end))
            sub.save()
        except UserSubscription.DoesNotExist:
            pass
            
    return HttpResponse(status=200)
