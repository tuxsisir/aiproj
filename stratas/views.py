import re
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Membership, StrataPlan
from dockets.models import Incident, Bylaw

@login_required
@require_POST
def switch_strata(request, strata_id):
    """
    Switches active strata context in session for manager users.
    Rejects unauthorized access or non-manager council attempts.
    """
    # 1. Verify target membership exists and belongs to request.user
    target_membership = get_object_or_404(
        Membership.objects.select_related('strata'),
        user=request.user,
        strata_id=strata_id,
        is_active=True
    )

    # 2. RBAC Guard: Only users with MANAGER role can switch
    if target_membership.role != Membership.Role.STRATA_MANAGER:
        messages.error(request, "Permission denied: Council members are locked to their registered building.")
        return redirect(request.META.get('HTTP_REFERER', 'dashboard'))

    # 3. Store active strata ID in session
    request.session['active_strata_id'] = str(target_membership.strata.id)
    
    # 4. Optional: Save to User model if field exists for cross-browser persistence
    if hasattr(request.user, 'last_active_strata_id'):
        request.user.last_active_strata_id = target_membership.strata.id
        request.user.save(update_fields=['last_active_strata_id'])

    messages.success(request, f"Switched active workspace to {target_membership.strata.plan_number} - {target_membership.strata.name}")
    
    redirect_url = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(redirect_url)

@login_required
@require_POST
def leave_strata(request, strata_id):
    """
    Allows a Strata Manager to leave/remove their active membership from a specific StrataPlan.
    """
    target_membership = get_object_or_404(
        Membership.objects.select_related('strata'),
        user=request.user,
        strata_id=strata_id,
        is_active=True
    )

    if target_membership.role != Membership.Role.STRATA_MANAGER:
        messages.error(request, "Permission denied: Only managers can voluntarily leave a portfolio.")
        return redirect('dashboard')

    strata_name = target_membership.strata.name
    target_membership.delete()
    
    # If they just left their currently active session strata, clear it
    if request.session.get('active_strata_id') == str(strata_id):
        del request.session['active_strata_id']
        
    messages.success(request, f"You have successfully left the strata portfolio for {strata_name}.")
    
    # Check if they have other valid memberships to fallback to, otherwise go to onboarding
    if Membership.objects.filter(user=request.user, is_active=True).exists():
        return redirect('dashboard')
    else:
        return redirect('onboarding')

@login_required
def building_members_list(request):
    """
    Displays the directory of council members, strata managers, and caretakers 
    belonging to the current active strata.
    """
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')

    memberships_list = (
        Membership.objects.filter(strata=request.strata, is_active=True)
        .select_related('user')
        .order_by('role', 'joined_at')
    )
    
    paginator = Paginator(memberships_list, 10) # 10 members per page
    page_number = request.GET.get('page')
    memberships = paginator.get_page(page_number)

    return render(request, 'stratas/members_list.html', {
        'memberships': memberships,
    })

@login_required
def onboarding_wizard(request):
    has_membership = request.user.memberships.filter(is_active=True).exists()
    is_manager = request.user.memberships.filter(is_active=True, role=Membership.Role.STRATA_MANAGER).exists()
    
    if has_membership and not is_manager:
        return redirect('dockets:incident_list')

    if request.method == "POST":
        persona = request.POST.get('persona')
        plan_number = request.POST.get('plan_number', '').strip().upper()
        name = request.POST.get('name', '').strip()
        unit_number = request.POST.get('unit_number', '').strip()
        role = request.POST.get('role', '')
        phone_number = request.POST.get('phone_number', '').strip()
        brokerage_name = request.POST.get('brokerage_name', '').strip()

        # Update user lead fields
        request.user.phone_number = phone_number
        if persona == 'MANAGER':
            request.user.brokerage_name = brokerage_name
            role = Membership.Role.STRATA_MANAGER
        request.user.save(update_fields=['phone_number', 'brokerage_name'])

        # Validate BC Strata Plan regex
        if not re.match(r'^(EPS|BCS|LMS|NWS|VIS|KAS|PRS)\s?\d{1,6}$', plan_number):
            messages.error(request, "Invalid Strata Plan format. Must be EPS, BCS, etc. followed by numbers.")
            return render(request, 'stratas/onboarding.html')
            
        plan_number = plan_number.replace(" ", "")

        # Check existing
        strata, created = StrataPlan.objects.get_or_create(
            plan_number=plan_number,
            defaults={'name': name}
        )

        if not created:
            # Prevent duplicate claim
            return render(request, 'stratas/already_claimed.html', {'strata': strata})

        # Create Membership
        Membership.objects.create(
            user=request.user,
            strata=strata,
            role=role,
            unit_number=unit_number,
            is_active=True
        )

        request.session['active_strata_id'] = str(strata.id)
        request.strata = strata
        
        # Seed Mock Incident
        bylaw = Bylaw.objects.filter(strata=strata, code='3(4)').first()
        Incident.objects.create(
            strata=strata,
            created_by=request.user,
            incident_type=Incident.Type.BYLAW,
            title="Sample Docket: Noise & Quiet Enjoyment Infraction",
            unit_number="Sample Unit",
            bylaw=bylaw,
            description="This is a demo incident generated during onboarding. A resident complained about excessive noise.",
            status=Incident.Status.PENDING_MANAGER
        )

        messages.success(request, f"Welcome to CivicDesk! Workspace for {strata.plan_number} is ready.")
        return redirect('dockets:incident_list')

    return render(request, 'stratas/onboarding.html')
