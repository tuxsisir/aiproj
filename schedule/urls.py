from django.urls import path

from . import views

app_name = "schedule"

urlpatterns = [
    path("", views.calendar_month, name="month"),
    path("dates/new/", views.key_date_create, name="key_date_create"),
    path("dates/<uuid:pk>/", views.key_date_update, name="key_date_update"),
    path("dates/<uuid:pk>/delete/", views.key_date_delete, name="key_date_delete"),
]
