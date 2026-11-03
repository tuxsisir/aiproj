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
    path('<uuid:pk>/pdf/', views.generate_fine_pdf, name='generate_fine_pdf'),
    path('<uuid:pk>/evidence/', views.incident_evidence, name='incident_evidence'),
    path('events/<uuid:pk>/file/', views.event_file, name='event_file'),

    # Bylaw Management
    path('bylaws/', views.bylaw_list, name='bylaw_list'),
    path('bylaws/new/', views.bylaw_create, name='bylaw_create'),
    path('bylaws/<uuid:pk>/edit/', views.bylaw_update, name='bylaw_update'),
    path('bylaws/<uuid:pk>/archive/', views.bylaw_archive_toggle, name='bylaw_archive_toggle'),

    # Public Zero-Login Portals
    path('actions/manager/<uuid:token>/', views.manager_magic_action, name='manager_magic_action'),
    path('respond/<uuid:token>/', views.owner_response_portal, name='owner_response_portal'),
    path('respond/<uuid:token>/evidence/', views.owner_evidence, name='owner_evidence'),
    path('respond/<uuid:token>/file/', views.owner_submission_file, name='owner_submission_file'),
]
