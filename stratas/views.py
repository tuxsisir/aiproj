from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import OnboardingForm
from .models import Membership, StrataPlan
from . import services


def _safe_referer(request, fallback='dashboard'):
    referer = request.META.get('HTTP_REFERER')
    if referer and url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
        return referer
    return fallback


@login_required
@require_POST
def switch_strata(request, strata_id):
    """
    Switches active strata context in session for manager users.
    Rejects unauthorized access or non-manager council attempts.
    """
    target_membership = get_object_or_404(
        Membership.objects.active().select_related('strata'),
        user=request.user,
        strata_id=strata_id,
    )

    if not target_membership.is_manager:
        messages.error(request, "Permission denied: Council members are locked to their registered building.")
        return redirect(_safe_referer(request))

    request.session['active_strata_id'] = str(target_membership.strata.id)
    messages.success(request, f"Switched active workspace to {target_membership.strata.plan_number} - {target_membership.strata.name}")
    return redirect(_safe_referer(request))


@login_required
@require_POST
def leave_strata(request, strata_id):
    """
    Allows a Strata Manager to leave a specific StrataPlan. The membership is deactivated, not deleted.
    """
    target_membership = get_object_or_404(
        Membership.objects.active().select_related('strata'),
        user=request.user,
        strata_id=strata_id,
    )

    if not target_membership.is_manager:
        messages.error(request, "Permission denied: Only managers can voluntarily leave a portfolio.")
        return redirect('dashboard')

    services.leave_strata(target_membership)

    if request.session.get('active_strata_id') == str(strata_id):
        del request.session['active_strata_id']

    messages.success(request, f"You have successfully left the strata portfolio for {target_membership.strata.name}.")

    if Membership.objects.active().filter(user=request.user).exists():
        return redirect('dashboard')
    return redirect('onboarding')


@login_required
def building_members_list(request):
    """
    Displays the directory of council members and strata managers belonging to the current active strata.
    """
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')

    memberships_list = (
        Membership.objects.active().filter(strata=request.strata)
        .select_related('user')
        .order_by('role', 'position', 'joined_at')
    )

    paginator = Paginator(memberships_list, 10) # 10 members per page
    memberships = paginator.get_page(request.GET.get('page'))

    return render(request, 'stratas/members_list.html', {
        'memberships': memberships,
    })


@login_required
def onboarding_wizard(request):
    """
    Request access to a building (existing or new). Every request waits for platform-admin approval.
    Council members belong to one building; managers may come back here to add more.
    """
    # The platform admin approves requests and never makes them, even if it also holds a membership.
    if request.user.is_superuser:
        return redirect('admin:index')
    memberships = request.user.memberships.all()
    if memberships.pending().exists():
        return redirect('membership_pending')
    active = memberships.active()
    if active.exists() and not active.managers().exists():
        return redirect('dashboard')

    form = OnboardingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        is_council = data['persona'] == Membership.Role.COUNCIL

        request.user.phone_number = data['phone_number'].strip()
        if not is_council:
            request.user.brokerage_name = data['brokerage_name'].strip()
        request.user.save(update_fields=['phone_number', 'brokerage_name'])

        strata = data['strata_id'] or services.create_strata(
            plan_number=data['plan_number'],
            name=data['name'].strip(),
            created_by=request.user,
        )
        services.request_membership(
            user=request.user,
            strata=strata,
            role=data['persona'],
            position=data['position'] if is_council else '',
            unit_number=data['unit_number'].strip() if is_council else '',
        )
        return redirect('membership_pending')

    for errors in form.errors.values():
        for error in errors:
            messages.error(request, error)

    return render(request, 'stratas/onboarding.html', {
        'existing_stratas': StrataPlan.objects.order_by('plan_number'),
        'positions': Membership.Position.choices,
    })


@login_required
def membership_pending(request):
    pending = request.user.memberships.pending().select_related('strata')
    if not pending.exists():
        return redirect('dashboard')
    return render(request, 'stratas/membership_pending.html', {'pending': pending})
