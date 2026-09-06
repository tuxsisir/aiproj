from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("dashboard/", views.dashboard_demo, name="dashboard_demo"),
    path("documents/", views.documents, name="documents"),
    path("queries/", views.queries, name="queries"),
    path("chat-response/", views.chat_response, name="chat_response"),
]
