from django.urls import path

from . import views

app_name = "meetings"

urlpatterns = [
    path("", views.meeting_list, name="list"),
    path("new/", views.meeting_create, name="create"),
    path("<uuid:pk>/", views.meeting_detail, name="detail"),
    path("<uuid:pk>/minutes/", views.meeting_minutes, name="minutes"),
    path("<uuid:pk>/record/", views.meeting_record, name="record"),
    path("<uuid:pk>/approve/", views.meeting_approve, name="approve"),
    path("<uuid:pk>/cancel/", views.meeting_cancel, name="cancel"),
    path("<uuid:pk>/items/add/", views.item_add, name="item_add"),
    path("items/<uuid:pk>/move/", views.item_move, name="item_move"),
    path("items/<uuid:pk>/remove/", views.item_remove, name="item_remove"),
]
