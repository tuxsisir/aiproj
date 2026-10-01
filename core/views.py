import json
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

stripe.api_key = settings.STRIPE_SECRET_KEY


def landing_page(request):
    """Public landing page."""
    return render(request, "landing.html")


from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
from dockets.models import Incident, Bylaw

@login_required
def dashboard(request):
    """Protected dashboard area with metrics and charts."""
    if not request.strata:
        return render(request, "dashboard.html", {
            'active_incidents': 0, 'pending_votes': 0, 'deadlines_active': 0, 'resolved_this_month': 0,
            'activity_chart_data': {}, 'breakdown_chart_data': {}, 'recent_incidents': []
        })

    incidents = Incident.objects.filter(strata=request.strata)
    
    # KPIs
    active_incidents = incidents.exclude(status__in=[Incident.Status.RESOLVED_FINED, Incident.Status.RESOLVED_DISMISSED]).count()
    pending_votes = incidents.filter(status=Incident.Status.VOTING_OPEN).count()
    deadlines_active = incidents.filter(status__in=[Incident.Status.NOTICE_ISSUED, Incident.Status.RESPONSE_RECEIVED]).count()
    
    now = timezone.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    resolved_this_month = incidents.filter(
        status__in=[Incident.Status.RESOLVED_FINED, Incident.Status.RESOLVED_DISMISSED],
        updated_at__gte=start_of_month
    ).count()

    # Chart 1: Activity Timeline (Last 6 Months)
    months_labels = []
    notices_issued = []
    resolved_files = []
    
    for i in range(5, -1, -1):
        target_month = now - timedelta(days=30 * i)
        start = target_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # End of the month approximation
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
            
        months_labels.append(start.strftime("%b"))
        
        # Count notices issued
        issued = incidents.filter(created_at__gte=start, created_at__lt=end).count()
        notices_issued.append(issued)
        
        # Count resolved files
        resolved = incidents.filter(
            status__in=[Incident.Status.RESOLVED_FINED, Incident.Status.RESOLVED_DISMISSED],
            updated_at__gte=start, updated_at__lt=end
        ).count()
        resolved_files.append(resolved)
        
    activity_chart_data = {
        'labels': months_labels,
        'series': [
            {'name': 'Notices Issued', 'data': notices_issued},
            {'name': 'Resolved Files', 'data': resolved_files}
        ]
    }

    # Chart 2: Breakdown by Category
    active_qs = incidents.exclude(status__in=[Incident.Status.RESOLVED_FINED, Incident.Status.RESOLVED_DISMISSED])
    breakdown_qs = active_qs.values('bylaw__title').annotate(count=Count('id')).order_by('-count')[:5]
    
    breakdown_labels = []
    breakdown_series = []
    for item in breakdown_qs:
        title = item['bylaw__title'] if item['bylaw__title'] else 'Deficiency'
        breakdown_labels.append(title)
        breakdown_series.append(item['count'])

    if not breakdown_series:
        breakdown_labels = ["No Active Incidents"]
        breakdown_series = [0]

    breakdown_chart_data = {
        'labels': breakdown_labels,
        'series': breakdown_series,
        'total': active_incidents
    }

    recent_incidents = incidents.select_related('bylaw', 'created_by').order_by('-created_at')[:5]

    context = {
        'active_incidents': active_incidents,
        'pending_votes': pending_votes,
        'deadlines_active': deadlines_active,
        'resolved_this_month': resolved_this_month,
        'activity_chart_data': activity_chart_data,
        'breakdown_chart_data': breakdown_chart_data,
        'recent_incidents': recent_incidents,
    }
    return render(request, "dashboard.html", context)


@login_required
def profile_edit(request):
    """Edit user profile and avatar."""
    if request.method == "POST":
        user = request.user
        
        # Handle avatar upload
        if 'avatar' in request.FILES:
            user.avatar = request.FILES['avatar']
            
        # Handle other info
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        
        if not first_name or not last_name:
            messages.error(request, "First name and last name are required.")
            return redirect('profile_edit')
            
        user.first_name = first_name
        user.last_name = last_name
        user.save()
        messages.success(request, "Profile updated successfully.")
        return redirect('profile_edit')
        
    return render(request, "profile_edit.html")



