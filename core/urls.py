from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile_edit, name="profile_edit"),
    path("checkout/", views.create_checkout_session, name="create_checkout_session"),
    path("webhooks/stripe/", views.stripe_webhook, name="stripe_webhook"),
]
