from django.urls import path

from . import views

app_name = "inbox"

urlpatterns = [
    path("", views.inbox_home, name="home"),
    path("<uuid:pk>/", views.email_detail, name="detail"),
    path("<uuid:pk>/summary/", views.email_summary, name="summary"),
    path("<uuid:pk>/retry/", views.email_retry, name="retry"),
]
