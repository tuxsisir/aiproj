from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from stratas.decorators import membership_required
from . import services
from .forms import AgendaItemForm, HeldForm, MeetingForm, MinutesForm, MoveForm
from .models import AgendaItem, Meeting

MinutesFormSet = modelformset_factory(AgendaItem, form=MinutesForm, extra=0)


@membership_required
def meeting_list(request):
    now = timezone.now()
    groups = {"upcoming": [], "unrecorded": [], "awaiting": [], "past": []}
    for meeting in request.strata.meetings.all():
        if meeting.status == Meeting.Status.PLANNED:
            groups["upcoming" if meeting.starts_at >= now else "unrecorded"].append(meeting)
        elif meeting.status == Meeting.Status.HELD:
            groups["awaiting"].append(meeting)
        else:
            groups["past"].append(meeting)
    groups["upcoming"].reverse()  # soonest first
    return render(request, "meetings/list.html", groups)


@membership_required
def meeting_create(request):
    issues, cases = services.open_items(request.strata)
    form = MeetingForm(request.POST or None, issues=issues, cases=cases)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        meeting = services.plan_meeting(
            request.strata, request.user, kind=data["kind"], starts_at=data["starts_at"],
            location=data["location"], issues=data["issues"], cases=data["cases"], request=request,
        )
        messages.success(request, f"{meeting} planned. Everyone on council has the agenda.")
        return redirect("meetings:detail", pk=meeting.pk)
    return render(request, "meetings/form.html", {"form": form})


@membership_required
def meeting_detail(request, pk):
    meeting = _get_meeting(request, pk)
    return _render_detail(request, meeting)


@membership_required
@require_POST
def item_add(request, pk):
    meeting = _get_meeting(request, pk)
    if not meeting.agenda_editable:
        return _locked(request, meeting)
    form = AgendaItemForm(request.POST)
    if form.is_valid():
        services.add_item(meeting, **form.cleaned_data, user=request.user, request=request)
        messages.success(request, "Added to the agenda.")
        return redirect("meetings:detail", pk=meeting.pk)
    return _render_detail(request, meeting, item_form=form, status=400)


@membership_required
@require_POST
def item_move(request, pk):
    item = _get_item(request, pk)
    form = MoveForm(request.POST)
    if item.meeting.agenda_editable and form.is_valid():
        services.move_item(item, up=form.cleaned_data["direction"] == "up")
    return redirect("meetings:detail", pk=item.meeting_id)


@membership_required
@require_POST
def item_remove(request, pk):
    item = _get_item(request, pk)
    if not item.meeting.agenda_editable:
        return _locked(request, item.meeting)
    services.remove_item(item, request.user, request=request)
    messages.success(request, f"Removed “{item.title}” from the agenda.")
    return redirect("meetings:detail", pk=item.meeting_id)


@membership_required
@require_POST
def meeting_record(request, pk):
    """Save the minutes of every item; with action=held, also record attendance and mark the meeting held."""
    meeting = _get_meeting(request, pk)
    if not meeting.minutes_editable:
        return _locked(request, meeting)
    items = meeting.items.all()
    formset = MinutesFormSet(request.POST, queryset=items)
    marking_held = request.POST.get("action") == "held" and meeting.status == Meeting.Status.PLANNED
    held_form = HeldForm(request.POST if marking_held else None, meeting=meeting)

    if formset.is_valid() and not _same_items(formset, items):  # a stale page or an edited POST
        messages.error(request, "The agenda changed since this page was opened. Reload it and enter the minutes again.")
        return redirect("meetings:detail", pk=meeting.pk)
    if formset.is_valid() and (not marking_held or held_form.is_valid()):
        with transaction.atomic():
            for form in formset.forms:
                services.record_minutes(form.instance, minutes=form.cleaned_data["minutes"],
                                        decision=form.cleaned_data["decision"], user=request.user, request=request)
            held = marking_held and services.mark_held(meeting, request.user, request=request,
                                                       **held_form.cleaned_data)
        if held:
            messages.success(request, "Meeting recorded as held. Council has been asked to approve the minutes.")
        else:
            messages.success(request, "Minutes saved.")
        return redirect("meetings:detail", pk=meeting.pk)
    return _render_detail(request, meeting, formset=formset, held_form=held_form, tab="minutes", status=400)


@membership_required
@require_POST
def meeting_approve(request, pk):
    meeting = _get_meeting(request, pk)
    if not request.membership.is_council:
        raise PermissionDenied("Only council approves minutes.")
    if meeting.status != Meeting.Status.HELD:
        return _locked(request, meeting)
    if services.approve_minutes(meeting, request.user, request=request):
        messages.success(request, "Minutes approved. Decisions were posted to their issues and cases.")
    return redirect("meetings:detail", pk=meeting.pk)


@membership_required
@require_POST
def meeting_cancel(request, pk):
    meeting = _get_meeting(request, pk)
    if not meeting.agenda_editable:
        return _locked(request, meeting)
    services.cancel_meeting(meeting, request.user, request=request)
    messages.success(request, f"{meeting} cancelled.")
    return redirect("meetings:list")


@membership_required
def meeting_minutes(request, pk):
    """Printable minutes. ?copy=owners leaves out in-camera items' details (what owners may request)."""
    meeting = _get_meeting(request, pk)
    owners_copy = request.GET.get("copy") == "owners"
    return render(request, "meetings/minutes.html", {
        "meeting": meeting,
        "items": meeting.items.all(),
        "attendees": meeting.attendees.order_by("first_name", "email"),
        "owners_copy": owners_copy,
    })


def _render_detail(request, meeting, *, item_form=None, formset=None, held_form=None, tab=None, status=200):
    items = meeting.items.select_related("issue", "incident")
    if formset is None and meeting.minutes_editable:
        formset = MinutesFormSet(queryset=items)
    started = meeting.starts_at <= timezone.now()
    return render(request, "meetings/detail.html", {
        "meeting": meeting,
        "items": items,
        "formset": formset,
        "item_form": item_form or AgendaItemForm(),
        "held_form": held_form or HeldForm(meeting=meeting),
        "attendees": meeting.attendees.order_by("first_name", "email"),
        "tab": tab or ("minutes" if started or not meeting.agenda_editable else "agenda"),
        "can_approve": request.membership.is_council and meeting.status == Meeting.Status.HELD,
    }, status=status)


def _same_items(formset, items):
    """The posted rows are exactly this meeting's agenda items, each once."""
    posted = [form.instance.pk for form in formset.forms]
    return len(posted) == len(set(posted)) and set(posted) == {item.pk for item in items}


def _locked(request, meeting):
    messages.error(request, f"This meeting is {meeting.get_status_display().lower()}; that can't be changed now.")
    return redirect("meetings:detail", pk=meeting.pk)


def _get_meeting(request, pk):
    return get_object_or_404(Meeting.objects.select_related("created_by", "approved_by"), pk=pk,
                             strata=request.strata)


def _get_item(request, pk):
    return get_object_or_404(AgendaItem.objects.select_related("meeting"), pk=pk, meeting__strata=request.strata)
