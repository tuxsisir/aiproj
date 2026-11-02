import calendar
import datetime

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from stratas.decorators import membership_required

from . import feed, services
from .forms import KeyDateForm, MonthForm
from .models import KeyDate

WEEK = calendar.Calendar(firstweekday=6)  # weeks start on Sunday
HIGHLIGHT_ORDER = {"overdue": 0, "soon": 1, "": 2, "done": 3, "past": 3}  # what a month card shows first


@membership_required
def calendar_month(request):
    today = timezone.localdate()
    first = MonthForm(request.GET).first_day(today)
    weeks = WEEK.monthdatescalendar(first.year, first.month)
    prev_month, next_month = _shift(first, -1), _shift(first, 1)
    # One query window covers the grid (with spill-over days) and the three month cards.
    span_end = _shift(first, 2) - datetime.timedelta(days=1)
    events = feed.events_between(request.strata, min(prev_month, weeks[0][0]), max(span_end, weeks[-1][-1]))

    by_day = {}
    for event in events:
        by_day.setdefault(event.date, []).append(event)
    months = []
    for m in (prev_month, first, next_month):
        dated = [e for e in events if (e.date.year, e.date.month) == (m.year, m.month)]
        months.append({
            "first": m,
            "events": dated,
            "overdue": sum(e.status == "overdue" for e in dated),
            "highlights": sorted(dated, key=lambda e: (HIGHLIGHT_ORDER.get(e.status, 2), e.date))[:3],
            "is_current": m == first,
        })
    month_events = months[1]["events"]

    return render(
        request,
        "schedule/month.html",
        {
            "month": first,
            "prev_month": prev_month,
            "next_month": next_month,
            "months": months,
            "this_month": today.replace(day=1),
            "today": today,
            "weekdays": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
            "weeks": [[(day, by_day.get(day, [])) for day in week] for week in weeks],
            "month_events": month_events,
            "overdue_count": sum(e.status == "overdue" for e in month_events),
            "still_overdue": feed.still_overdue(request.strata, first)
            if first == today.replace(day=1)
            else [],
        },
    )


@membership_required
def key_date_create(request):
    form = KeyDateForm(request.POST or None, initial={"date": _clicked_day(request)})
    if request.method == "POST" and form.is_valid():
        key_date = services.create_key_date(
            request.strata, request.user, request=request, **form.cleaned_data
        )
        messages.success(request, f"Added {key_date.title}.")
        return redirect(_month_url(key_date.date))
    return render(request, "schedule/key_date_form.html", {"form": form})


@membership_required
def key_date_update(request, pk):
    key_date = get_object_or_404(KeyDate, pk=pk, strata=request.strata)
    saved = {"title": key_date.title, "date": key_date.date}  # header shows these, not unsaved edits
    form = KeyDateForm(request.POST or None, instance=key_date)
    if request.method == "POST" and form.is_valid():
        services.update_key_date(form.instance, request.user, request=request)
        messages.success(request, f"Saved {key_date.title}.")
        return redirect(_month_url(key_date.date))
    return render(
        request,
        "schedule/key_date_form.html",
        {"form": form, "key_date": key_date, "saved": saved},
    )


@membership_required
@require_POST
def key_date_delete(request, pk):
    key_date = get_object_or_404(KeyDate, pk=pk, strata=request.strata)
    title, day = key_date.title, key_date.date
    services.delete_key_date(key_date, request.user, request=request)
    messages.success(request, f"Removed {title}.")
    return redirect(_month_url(day))


def _clicked_day(request):
    try:
        return forms.DateField().clean(request.GET.get("date"))
    except forms.ValidationError:
        return None


def _shift(first, months):
    index = first.year * 12 + first.month - 1 + months
    return datetime.date(index // 12, index % 12 + 1, 1)


def _month_url(day):
    return f"{reverse('schedule:month')}?month={day:%Y-%m}"
