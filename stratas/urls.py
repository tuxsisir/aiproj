from django.urls import path
from . import views

urlpatterns = [
    path('onboarding/', views.onboarding_wizard, name='onboarding'),
    path('switch/<uuid:strata_id>/', views.switch_strata, name='switch_strata'),
    path('leave/<uuid:strata_id>/', views.leave_strata, name='leave_strata'),
    path('members/', views.building_members_list, name='building_members'),
]
