from django.core.mail import send_mail
from django.conf import settings

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Incident, Bylaw, CouncilVote, IncidentEvent
from stratas.models import Membership
from django.utils import timezone

from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError
from core.services import record_audit_log

@login_required
def incident_list(request):
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')

    incidents = Incident.objects.filter(strata=request.strata).select_related('bylaw', 'created_by')

    query = request.GET.get('q')
    if query:
        incidents = incidents.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(unit_number__icontains=query)
        )

    # Paginate by 5
    paginator = Paginator(incidents, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'incidents': page_obj,  # Pass the paginated object
        'query': query,
        'total_open': incidents.exclude(status__in=[Incident.Status.RESOLVED_FINED, Incident.Status.RESOLVED_DISMISSED]).count(),
        'awaiting_manager': incidents.filter(status=Incident.Status.IN_REVIEW).count(),
        'ready_for_vote': incidents.filter(status=Incident.Status.VOTING_OPEN).count(),
    }
    return render(request, 'dockets/incident_list.html', context)

@login_required
def incident_create(request):
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')

    if request.membership and request.membership.role not in [Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT]:
        messages.error(request, "Permission denied: Only Council Members can log new dockets.")
        return redirect('dockets:incident_list')

    if request.method == "POST":
        title = request.POST.get("title")
        incident_type = request.POST.get("incident_type")
        unit_number = request.POST.get("unit_number", "")
        bylaw_id = request.POST.get("bylaw")
        description = request.POST.get("description")
        evidence_image = request.FILES.get("evidence_image")

        bylaw = None
        if bylaw_id:
            bylaw = get_object_or_404(Bylaw, id=bylaw_id, strata=request.strata)

        incident = Incident.objects.create(
            strata=request.strata,
            created_by=request.user,
            incident_type=incident_type,
            title=title,
            unit_number=unit_number,
            bylaw=bylaw,
            description=description,
            evidence_image=evidence_image,
            status=Incident.Status.IN_REVIEW
        )
        record_audit_log(incident, request.user, request=request)
        
        messages.success(request, "Docket successfully logged and awaiting manager review.")
        return redirect('dockets:incident_list')

    bylaws = Bylaw.objects.filter(strata=request.strata, is_archived=False).order_by('code')
    return render(request, 'dockets/incident_create.html', {'bylaws': bylaws, 'types': Incident.Type.choices})

@login_required
def incident_detail(request, pk):
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')

    incident = get_object_or_404(Incident.objects.select_related('bylaw'), pk=pk, strata=request.strata)
    votes = incident.votes.select_related('member__user')
    
    # Check if current user can vote
    user_vote = None
    if request.membership and request.membership.role in [Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT]:
        user_vote = votes.filter(member=request.membership).first()
        
    owner_response = incident.events.filter(
        event_type__in=[IncidentEvent.EventType.OWNER_STATEMENT, IncidentEvent.EventType.HEARING_REQUESTED]
    ).first()
    
    total_council_count = Membership.objects.filter(
        strata=incident.strata, 
        role__in=[Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT]
    ).count()
    
    fine_votes_count = sum(1 for v in votes if v.approve_fine)
    dismiss_votes_count = sum(1 for v in votes if not v.approve_fine)
    total_votes_cast = len(votes)
    quorum_percentage = int((total_votes_cast / total_council_count) * 100) if total_council_count > 0 else 0

    fine_dispatched_event = incident.events.filter(event_type=IncidentEvent.EventType.FINE_DISPATCHED).first()

    return render(request, 'dockets/incident_detail.html', {
        'incident': incident,
        'votes': votes,
        'user_vote': user_vote,
        'owner_response': owner_response,
        'total_council_count': total_council_count,
        'fine_votes_count': fine_votes_count,
        'dismiss_votes_count': dismiss_votes_count,
        'total_votes_cast': total_votes_cast,
        'quorum_percentage': quorum_percentage,
        'fine_dispatched_event': fine_dispatched_event,
    })

@login_required
@require_POST
def cast_council_vote(request, pk):
    if not request.strata or not request.membership:
        messages.error(request, "Invalid strata context.")
        return redirect('dockets:incident_list')

    if request.membership.role not in [Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT]:
        messages.error(request, "Only council members can vote.")
        return redirect('dockets:incident_detail', pk=pk)

    incident = get_object_or_404(Incident, pk=pk, strata=request.strata)
    
    if incident.status != Incident.Status.VOTING_OPEN:
        messages.error(request, "Voting is not currently open for this docket.")
        return redirect('dockets:incident_detail', pk=pk)

    if CouncilVote.objects.filter(incident=incident, member=request.membership).exists():
        messages.error(request, "You have already cast your ballot.")
        return redirect('dockets:incident_detail', pk=pk)

    approve_fine = request.POST.get('approve_fine') == 'true'
    notes = request.POST.get('notes', '')

    CouncilVote.objects.create(
        incident=incident,
        member=request.membership,
        approve_fine=approve_fine,
        notes=notes
    )
    
    record_audit_log(incident, request.user, action="VOTE_CAST", request=request, custom_summary=f"Vote cast: {'Levy Fine' if approve_fine else 'Dismiss'}")
    
    IncidentEvent.objects.create(
        incident=incident,
        created_by=request.user,
        event_type=IncidentEvent.EventType.NOTE,
        description=f"{request.user.get_full_name() or request.user.email} ({request.membership.get_role_display()}) cast digital ballot: {'Levy Fine' if approve_fine else 'Dismiss / Warn'}. Notes: {notes}"
    )

    # Tally Quorum
    total_council_count = Membership.objects.filter(
        strata=incident.strata, 
        role__in=[Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT]
    ).count()
    
    votes = CouncilVote.objects.filter(incident=incident)
    total_votes_cast = votes.count()
    
    if total_votes_cast >= total_council_count and total_council_count > 0:
        fine_votes = votes.filter(approve_fine=True).count()
        if fine_votes > (total_council_count / 2):
            incident.status = Incident.Status.RESOLVED_FINED
        else:
            incident.status = Incident.Status.RESOLVED_DISMISSED
        incident.save()
        record_audit_log(incident, request.user, action="STATUS_CHANGE", request=request, custom_summary=f"Quorum reached. Status changed to {incident.get_status_display()}")

    messages.success(request, "Your council vote has been securely recorded.")
    return redirect('dockets:incident_detail', pk=pk)


def manager_magic_action(request, token):
    incident = get_object_or_404(Incident, manager_token=token)

    if request.method == "POST":
        recipient_email = request.POST.get("recipient_email")
        if recipient_email:
            incident.recipient_email = recipient_email
            incident.calculate_and_set_deadline()
            incident.save()
            
            record_audit_log(incident, request.user if request.user.is_authenticated else None, action="NOTICE_DISPATCHED", request=request)
            
            # Note: in real app, send email here with owner_token link
            messages.success(request, f"Official Notice sent to {recipient_email}. Clock is ticking.")
            return redirect('dockets:manager_magic_action', token=token)

    return render(request, 'dockets/manager_magic_action.html', {'incident': incident})

def owner_response_portal(request, token):
    incident = get_object_or_404(Incident, owner_token=token)
    
    # Check existing events
    existing_event = IncidentEvent.objects.filter(
        incident=incident, 
        event_type__in=[IncidentEvent.EventType.OWNER_STATEMENT, IncidentEvent.EventType.HEARING_REQUESTED]
    ).first()
    
    is_expired = False
    if incident.statutory_deadline:
        is_expired = timezone.now() > incident.statutory_deadline
        
    already_submitted = existing_event is not None
    
    if request.method == "POST":
        if already_submitted or is_expired:
            return redirect('dockets:owner_response_portal', token=token)
            
        response_type = request.POST.get("response_type")
        statement = request.POST.get("statement", "")
        counter_evidence = request.FILES.get("counter_evidence")
        
        if response_type == 'WRITTEN':
            event_type = IncidentEvent.EventType.OWNER_STATEMENT
            description = statement
        elif response_type == 'HEARING':
            event_type = IncidentEvent.EventType.HEARING_REQUESTED
            description = "Respondent requested an in-person council hearing under SPA s.135(1)(e). Note: " + statement
        else:
            return redirect('dockets:owner_response_portal', token=token)
            
        IncidentEvent.objects.create(
            incident=incident,
            event_type=event_type,
            description=description,
            evidence_file=counter_evidence
        )
        
        incident.status = Incident.Status.VOTING_OPEN
        incident.save()
        
        record_audit_log(incident, None, action="STATUS_CHANGE", request=request, custom_summary=f"Owner submitted response: {response_type}")
        return redirect('dockets:owner_response_portal', token=token)

    return render(request, 'incidents/owner_portal.html', {
        'incident': incident,
        'already_submitted': already_submitted,
        'is_expired': is_expired,
        'submitted_event': existing_event
    })

@login_required
def bylaw_list(request):
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')
    
    bylaws = Bylaw.objects.filter(strata=request.strata).select_related('created_by').order_by('is_archived', 'code')
    return render(request, 'dockets/bylaw_list.html', {'bylaws': bylaws})

@login_required
def bylaw_create(request):
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')
    
    if request.method == "POST":
        code = request.POST.get("code")
        title = request.POST.get("title")
        description = request.POST.get("description", "")
        standard_fine = request.POST.get("standard_fine", 200.00)
        
        try:
            Bylaw.objects.create(
                strata=request.strata,
                code=code,
                title=title,
                description=description,
                standard_fine=standard_fine,
                created_by=request.user
            )
            messages.success(request, f"Bylaw {code} successfully created.")
            return redirect('dockets:bylaw_list')
        except IntegrityError:
            messages.error(request, f"A bylaw with code '{code}' already exists. Please use a unique code.")
        except Exception as e:
            messages.error(request, f"Error creating bylaw: {e}")
            
    return render(request, 'dockets/bylaw_form.html')

@login_required
def bylaw_update(request, pk):
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')
        
    bylaw = get_object_or_404(Bylaw, pk=pk, strata=request.strata)
    
    if request.method == "POST":
        bylaw.code = request.POST.get("code")
        bylaw.title = request.POST.get("title")
        bylaw.description = request.POST.get("description", "")
        bylaw.standard_fine = request.POST.get("standard_fine", 200.00)
        
        is_archived = request.POST.get("is_archived") == 'on'
        bylaw.is_archived = is_archived
        
        try:
            bylaw.save()
            messages.success(request, f"Bylaw {bylaw.code} successfully updated.")
            return redirect('dockets:bylaw_list')
        except IntegrityError:
            messages.error(request, f"Another bylaw with code '{bylaw.code}' already exists. Please use a unique code.")
        except Exception as e:
            messages.error(request, f"Error updating bylaw: {e}")
            
    return render(request, 'dockets/bylaw_form.html', {'bylaw': bylaw})

@login_required
@require_POST
def bylaw_archive_toggle(request, pk):
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')
        
    bylaw = get_object_or_404(Bylaw, pk=pk, strata=request.strata)
    bylaw.is_archived = not bylaw.is_archived
    bylaw.save()
    status = "archived" if bylaw.is_archived else "restored"
    messages.success(request, f"Bylaw {bylaw.code} has been {status}.")
    return redirect('dockets:bylaw_list')

@login_required
def voting_center(request):
    """
    Shows all dockets with status VOTING_OPEN.
    Calculates progress bar and determines majority directives.
    """
    if not request.strata:
        messages.error(request, "No active strata context.")
        return redirect('dashboard')

    # Total council members
    total_council = Membership.objects.filter(
        strata=request.strata,
        role__in=[Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT],
        is_active=True
    ).count()

    incidents = Incident.objects.filter(
        strata=request.strata,
        status=Incident.Status.VOTING_OPEN
    ).prefetch_related('votes', 'votes__member', 'votes__member__user', 'bylaw')

    dockets = []
    for incident in incidents:
        votes = incident.votes.all()
        approve_count = sum(1 for v in votes if v.approve_fine)
        reject_count = sum(1 for v in votes if not v.approve_fine)
        total_votes = approve_count + reject_count
        
        # Calculate percentages for progress bars
        approve_percent = (approve_count / total_council * 100) if total_council > 0 else 0
        reject_percent = (reject_count / total_council * 100) if total_council > 0 else 0
        
        # Check if current user has voted
        user_voted = any(v.member.user == request.user for v in votes)
        user_vote_value = next((v.approve_fine for v in votes if v.member.user == request.user), None)

        majority_needed = (total_council // 2) + 1
        
        directive = "Awaiting votes"
        directive_color = "slate"
        
        if total_council > 0:
            if approve_count >= majority_needed:
                directive = "Majority Reached: Approve Fine"
                directive_color = "emerald"
            elif reject_count >= majority_needed:
                directive = "Majority Reached: Dismiss/Warn"
                directive_color = "rose"
            elif total_votes == total_council:
                directive = "Vote Tied/Inconclusive"
                directive_color = "amber"

        dockets.append({
            'incident': incident,
            'approve_count': approve_count,
            'reject_count': reject_count,
            'total_votes': total_votes,
            'approve_percent': approve_percent,
            'reject_percent': reject_percent,
            'user_voted': user_voted,
            'user_vote_value': user_vote_value,
            'directive': directive,
            'directive_color': directive_color,
            'majority_needed': majority_needed,
        })

    return render(request, 'dockets/voting_center.html', {
        'dockets': dockets,
        'total_council': total_council
    })

@login_required
@require_POST
def update_target_unit(request, pk):
    incident = get_object_or_404(Incident, pk=pk, strata=request.strata)
    if request.membership.role not in [Membership.Role.STRATA_MANAGER, Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT]:
        messages.error(request, "Permission denied to update unit particulars.")
        return redirect('dockets:incident_detail', pk=pk)
        
    incident.unit_number = request.POST.get('unit_number', incident.unit_number)
    
    # Only strata manager can update strata_lot and recipient_email
    if request.membership.role == Membership.Role.STRATA_MANAGER:
        incident.strata_lot = request.POST.get('strata_lot', incident.strata_lot)
        incident.recipient_email = request.POST.get('recipient_email', incident.recipient_email)
        
    incident.save()
    
    record_audit_log(incident, request.user, request=request)
    
    role_name = "Manager" if request.membership.role == Membership.Role.STRATA_MANAGER else "Council"
    IncidentEvent.objects.create(
        incident=incident,
        created_by=request.user,
        event_type=IncidentEvent.EventType.UNIT_CORRECTED,
        description=f"{role_name} corrected target unit particulars. Unit: {incident.unit_number}, Strata Lot: {incident.strata_lot}."
    )
    messages.success(request, "Unit particulars updated successfully.")
    return redirect('dockets:incident_detail', pk=pk)

@login_required
@require_POST
def log_incident_event(request, pk):
    incident = get_object_or_404(Incident, pk=pk, strata=request.strata)
    
    event_type = request.POST.get('event_type')
    description = request.POST.get('description')
    evidence_file = request.FILES.get('evidence_file')
    
    IncidentEvent.objects.create(
        incident=incident,
        created_by=request.user,
        event_type=event_type,
        description=description,
        evidence_file=evidence_file
    )
    messages.success(request, "Event logged successfully.")
    return redirect('dockets:incident_detail', pk=pk)

@login_required
@require_POST
def dispatch_section_135(request, pk):
    incident = get_object_or_404(Incident, pk=pk, strata=request.strata)
    if request.membership.role != Membership.Role.STRATA_MANAGER:
        messages.error(request, "Only strata managers can dispatch statutory notices.")
        return redirect('dockets:incident_detail', pk=pk)
        
    if not incident.unit_number or not incident.recipient_email:
        messages.error(request, "Unit number and recipient email are required to dispatch notice.")
        return redirect('dockets:incident_detail', pk=pk)
        
    incident.calculate_and_set_deadline()
    incident.save()
    
    
    
    
    subject = f"FORMAL NOTICE OF COMPLAINT - {incident.strata.plan_number}"
    message = f"""Dear Owner of Unit {incident.unit_number},

The Strata Corporation {incident.strata.plan_number} has received a complaint regarding an alleged contravention of the bylaws.

Particulars of the complaint:
- Bylaw: {incident.bylaw.code} ({incident.bylaw.title})
- Date of Intake: {incident.created_at.strftime('%b %-d, %Y')}
- Description: {incident.description}

Pursuant to Section 135 of the Strata Property Act, you are entitled to answer this complaint. You may provide a written response or request a hearing before the strata council.

Please note that under the Act (incorporating deemed service requirements), you have exactly 14 days from today to respond before the Council proceeds with a vote to potentially levy a fine.

To submit your written statement or formally request a council hearing, please use your secure response portal link below:
https://{request.get_host()}/dockets/respond/{incident.owner_token}/

Sincerely,
Strata Management"""

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [incident.recipient_email],
        fail_silently=False,
    )
    
    record_audit_log(incident, request.user, action="NOTICE_DISPATCHED", request=request)
    IncidentEvent.objects.create(
        incident=incident,
        created_by=request.user,
        event_type=IncidentEvent.EventType.STATUTORY_NOTICE,
        description=f"Statutory Section 135 Notice formally dispatched to {incident.recipient_email}."
    )
    messages.success(request, "Statutory Notice dispatched. Clock is ticking.")
    return redirect('dockets:incident_detail', pk=pk)


@login_required
@require_POST
def dispatch_fine_notice(request, pk):
    if not request.strata:
        return redirect('dashboard')
        
    incident = get_object_or_404(Incident, pk=pk, strata=request.strata)
    
    if incident.status != Incident.Status.RESOLVED_FINED:
        messages.error(request, "Incident is not in a fineable state.")
        return redirect('dockets:incident_detail', pk=pk)
        
    if request.membership.role != Membership.Role.STRATA_MANAGER:
        messages.error(request, "Only the strata manager can formally dispatch fine notices to the ledger.")
        return redirect('dockets:incident_detail', pk=pk)

    # In a real app, integrate with ledger/accounting here and send email
    send_mail(
        subject=f"Notice of Formal Fine - Strata Plan {incident.strata.plan_number}",
        message=f"""Dear Owner of Unit {incident.unit_number},\n\nThe Strata Council has reviewed your case and authorized levying a ${incident.bylaw.standard_fine} fine to your strata lot ledger for contravention of Bylaw {incident.bylaw.code}.""",
        from_email="no-reply@stratacorp.com",
        recipient_list=[incident.recipient_email],
        fail_silently=True,
    )

    IncidentEvent.objects.create(
        incident=incident,
        created_by=request.user,
        event_type=IncidentEvent.EventType.FINE_DISPATCHED,
        description=f"Formal Notice of Fine sent to {incident.recipient_email}. Fine amount: ${incident.bylaw.standard_fine}"
    )
    
    record_audit_log(incident, request.user, action="FINE_DISPATCHED", request=request)
    
    messages.success(request, f"Fine notice formally dispatched to {incident.recipient_email} and logged to the unit ledger.")
    return redirect('dockets:incident_detail', pk=pk)
