from django.urls import path
from . import views

app_name = 'dockets'

urlpatterns = [
    # Authenticated Dashboard Views
    path('', views.incident_list, name='incident_list'),
    path('voting/', views.voting_center, name='voting_center'),
    path('new/', views.incident_create, name='incident_create'),
    path('<uuid:pk>/', views.incident_detail, name='incident_detail'),
    path('<uuid:pk>/vote/', views.cast_council_vote, name='cast_council_vote'),
    path('<uuid:pk>/update-target/', views.update_target_unit, name='update_target_unit'),
    path('<uuid:pk>/log-event/', views.log_incident_event, name='log_incident_event'),
    path('<uuid:pk>/dispatch-notice/', views.dispatch_section_135, name='dispatch_section_135'),
    path('<uuid:pk>/dispatch-fine/', views.dispatch_fine_notice, name='dispatch_fine_notice'),

    # Bylaw Management
    path('bylaws/', views.bylaw_list, name='bylaw_list'),
    path('bylaws/new/', views.bylaw_create, name='bylaw_create'),
    path('bylaws/<uuid:pk>/edit/', views.bylaw_update, name='bylaw_update'),
    path('bylaws/<uuid:pk>/archive/', views.bylaw_archive_toggle, name='bylaw_archive_toggle'),

    # Public Zero-Login Portals
    path('actions/manager/<uuid:token>/', views.manager_magic_action, name='manager_magic_action'),
    path('respond/<uuid:token>/', views.owner_response_portal, name='owner_response_portal'),
]
