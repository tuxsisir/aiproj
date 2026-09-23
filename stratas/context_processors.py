def strata_context(request):
    if not request.user.is_authenticated:
        return {
            'active_strata': None,
            'active_membership': None,
            'user_memberships': [],
            'can_switch_strata': False,
        }

    user_memberships = list(
        request.user.memberships.select_related('strata').filter(is_active=True)
    )
    
    # Strata Managers always get the switcher so they can add new buildings
    is_manager = any(m.role == 'MANAGER' for m in user_memberships)
    can_switch = is_manager

    return {
        'active_strata': getattr(request, 'strata', None),
        'active_membership': getattr(request, 'membership', None),
        'user_memberships': user_memberships,
        'can_switch_strata': can_switch,
    }
