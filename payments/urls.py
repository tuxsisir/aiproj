from django.urls import path
from . import views

app_name = "payments"

urlpatterns = [
    path("checkout/", views.create_checkout_session, name="create_checkout_session"),
    path("portal/", views.customer_portal, name="customer_portal"),
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
]
