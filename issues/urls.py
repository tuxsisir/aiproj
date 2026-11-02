from django.urls import path

from . import views

app_name = "issues"

urlpatterns = [
    path("", views.issue_list, name="list"),
    path("new/", views.issue_create, name="create"),
    path("<uuid:pk>/", views.issue_detail, name="detail"),
    path("<uuid:pk>/update/", views.issue_update, name="update"),
]
