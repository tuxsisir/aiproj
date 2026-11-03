from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("healthz/", views.healthz, name="healthz"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("profile/", views.profile_edit, name="profile_edit"),
    path("profile/avatar/", views.my_avatar, name="my_avatar"),
]
