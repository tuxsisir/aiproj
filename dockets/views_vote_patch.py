def cast_council_vote_patch(request, pk):
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
