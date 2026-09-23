from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Incident, Bylaw, IncidentResponse, CouncilVote
from stratas.models import Membership

from django.core.paginator import Paginator
from django.db.models import Q
from django.db import IntegrityError

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
        'awaiting_manager': incidents.filter(status=Incident.Status.PENDING_MANAGER).count(),
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

        Incident.objects.create(
            strata=request.strata,
            created_by=request.user,
            incident_type=incident_type,
            title=title,
            unit_number=unit_number,
            bylaw=bylaw,
            description=description,
            evidence_image=evidence_image,
            status=Incident.Status.PENDING_MANAGER
        )
        messages.success(request, "Docket successfully logged and awaiting manager review.")
        return redirect('dockets:incident_list')

    bylaws = Bylaw.objects.filter(strata=request.strata, is_archived=False).order_by('code')
    return render(request, 'dockets/incident_create.html', {'bylaws': bylaws, 'types': Incident.Type.choices})

@login_required
def incident_detail(request, pk):
    if not request.strata:
        messages.warning(request, "No active strata plan selected.")
        return redirect('dashboard')

    incident = get_object_or_404(Incident.objects.select_related('bylaw', 'response'), pk=pk, strata=request.strata)
    votes = incident.votes.select_related('member__user')
    
    # Check if current user can vote
    user_vote = None
    if request.membership and request.membership.role in [Membership.Role.COUNCIL_MEMBER, Membership.Role.COUNCIL_PRESIDENT]:
        user_vote = votes.filter(member=request.membership).first()

    return render(request, 'dockets/incident_detail.html', {
        'incident': incident,
        'votes': votes,
        'user_vote': user_vote,
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
    approve_fine = request.POST.get('approve_fine') == 'true'
    notes = request.POST.get('notes', '')

    CouncilVote.objects.update_or_create(
        incident=incident,
        member=request.membership,
        defaults={'approve_fine': approve_fine, 'notes': notes}
    )
    messages.success(request, "Your council vote has been recorded.")
    return redirect('dockets:incident_detail', pk=pk)


def manager_magic_action(request, token):
    incident = get_object_or_404(Incident, manager_token=token)

    if request.method == "POST":
        recipient_email = request.POST.get("recipient_email")
        if recipient_email:
            incident.recipient_email = recipient_email
            incident.calculate_and_set_deadline()
            incident.save()
            # Note: in real app, send email here with owner_token link
            messages.success(request, f"Official Notice sent to {recipient_email}. Clock is ticking.")
            return redirect('dockets:manager_magic_action', token=token)

    return render(request, 'dockets/manager_magic_action.html', {'incident': incident})

def owner_response_portal(request, token):
    incident = get_object_or_404(Incident, owner_token=token)
    
    if hasattr(incident, 'response') or incident.status not in [Incident.Status.NOTICE_ISSUED]:
        return render(request, 'dockets/owner_response_portal.html', {'incident': incident, 'already_submitted': True})

    if request.method == "POST":
        response_type = request.POST.get("response_type")
        statement = request.POST.get("statement", "")
        counter_evidence = request.FILES.get("counter_evidence")

        IncidentResponse.objects.create(
            incident=incident,
            response_type=response_type,
            statement=statement,
            counter_evidence=counter_evidence
        )

        if response_type == IncidentResponse.ResponseType.HEARING:
            incident.status = Incident.Status.HEARING_REQUESTED
        else:
            incident.status = Incident.Status.RESPONSE_RECEIVED
        
        incident.save()
        return redirect('dockets:owner_response_portal', token=token)

    return render(request, 'dockets/owner_response_portal.html', {
        'incident': incident,
        'types': IncidentResponse.ResponseType.choices
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
