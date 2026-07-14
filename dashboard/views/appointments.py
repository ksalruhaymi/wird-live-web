"""Read-only appointments monitoring for admin/supervisor dashboard."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.appointments.access import (
    appointments_queryset_for,
    get_appointment_for_user,
)
from apps.appointments.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    AppointmentSlot,
    AppointmentStatus,
    SessionType,
    SlotStatus,
)
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.rbac.decorators import permissions_required

CANCELLED_STATUSES = (
    AppointmentStatus.CANCELLED_BY_STUDENT,
    AppointmentStatus.CANCELLED_BY_TEACHER,
    AppointmentStatus.REJECTED_BY_TEACHER,
)

MISSED_STATUSES = (
    AppointmentStatus.EXPIRED,
    AppointmentStatus.NO_SHOW_STUDENT,
    AppointmentStatus.NO_SHOW_TEACHER,
)

# Web monitoring requires global view permission (admin / supervisor).
_VIEW_ALL = ("dashboard.access", "appointments.view_all")


def _require_appointment(user, pk: int):
    appointment = get_appointment_for_user(user, pk)
    if appointment is None:
        raise Http404
    return appointment


def _apply_booking_filters(
    qs,
    *,
    bucket,
    status,
    session_type,
    date_from,
    date_to,
    q,
):
    now = timezone.now()
    today = timezone.localdate()

    if bucket == "today":
        qs = qs.filter(slot__start_at__date=today).exclude(status__in=CANCELLED_STATUSES)
    elif bucket == "upcoming":
        qs = qs.filter(status__in=ACTIVE_APPOINTMENT_STATUSES, slot__start_at__gte=now)
    elif bucket == "completed":
        qs = qs.filter(status=AppointmentStatus.COMPLETED)
    elif bucket == "cancelled":
        qs = qs.filter(status__in=CANCELLED_STATUSES)
    elif bucket == "missed":
        qs = qs.filter(status__in=MISSED_STATUSES)

    if status and status != "all":
        qs = qs.filter(status=status)
    if session_type and session_type != "all":
        qs = qs.filter(session_type=session_type)
    if date_from:
        qs = qs.filter(slot__start_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(slot__start_at__date__lte=date_to)
    if q:
        name_q = (
            Q(student__full_name__icontains=q)
            | Q(student__username__icontains=q)
            | Q(student__student_profile__display_name__icontains=q)
            | Q(teacher__full_name__icontains=q)
            | Q(teacher__username__icontains=q)
            | Q(teacher__teacher_profile__display_name__icontains=q)
        )
        if q.isdigit():
            name_q |= Q(pk=int(q))
        qs = qs.filter(name_q)
    return qs


def _status_badge_map():
    return {value: label for value, label in AppointmentStatus.choices}


def _period_stats(qs, *, days: int = 30):
    since = timezone.now() - timedelta(days=days)
    period = qs.filter(booked_at__gte=since)
    return period.aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status=AppointmentStatus.COMPLETED)),
        cancelled_by_student=Count(
            "id", filter=Q(status=AppointmentStatus.CANCELLED_BY_STUDENT)
        ),
        cancelled_by_teacher=Count(
            "id", filter=Q(status=AppointmentStatus.CANCELLED_BY_TEACHER)
        ),
        no_show=Count(
            "id",
            filter=Q(
                status__in=[
                    AppointmentStatus.NO_SHOW_STUDENT,
                    AppointmentStatus.NO_SHOW_TEACHER,
                ]
            ),
        ),
    )


@login_required
@permissions_required(*_VIEW_ALL)
@require_GET
def appointment_overview(request):
    now = timezone.now()
    today = timezone.localdate()
    week_end = now + timedelta(days=7)

    qs = appointments_queryset_for(request.user)
    stats = qs.aggregate(
        today_count=Count(
            "id",
            filter=Q(slot__start_at__date=today) & ~Q(status__in=CANCELLED_STATUSES),
        ),
        upcoming_count=Count(
            "id",
            filter=Q(status__in=ACTIVE_APPOINTMENT_STATUSES, slot__start_at__gte=now),
        ),
        completed_count=Count("id", filter=Q(status=AppointmentStatus.COMPLETED)),
        cancelled_count=Count("id", filter=Q(status__in=CANCELLED_STATUSES)),
    )
    available_slots_7d = AppointmentSlot.objects.filter(
        status=SlotStatus.AVAILABLE,
        start_at__gte=now,
        start_at__lte=week_end,
    ).count()

    period_stats = _period_stats(qs, days=30)
    avg_daily = round(period_stats["total"] / 30, 1) if period_stats["total"] else 0

    upcoming_preview = list(
        qs.filter(status__in=ACTIVE_APPOINTMENT_STATUSES, slot__start_at__gte=now)
        .order_by("slot__start_at", "id")[:8]
    )
    today_preview = list(
        qs.filter(slot__start_at__date=today)
        .exclude(status__in=CANCELLED_STATUSES)
        .order_by("slot__start_at", "id")[:8]
    )

    return render(
        request,
        "dashboard/pages/appointments/overview.html",
        {
            "active_tab": "overview",
            "stats": stats,
            "available_slots_7d": available_slots_7d,
            "period_stats": period_stats,
            "avg_daily": avg_daily,
            "upcoming_preview": upcoming_preview,
            "today_preview": today_preview,
            "status_labels": _status_badge_map(),
        },
    )


@login_required
@permissions_required(*_VIEW_ALL)
@require_GET
def appointment_all_list(request):
    bucket = (request.GET.get("bucket") or "all").strip()
    status = (request.GET.get("status") or "all").strip()
    session_type = (request.GET.get("session_type") or "all").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    q = (request.GET.get("q") or "").strip()

    qs = _apply_booking_filters(
        appointments_queryset_for(request.user).order_by("-slot__start_at", "-id"),
        bucket=bucket,
        status=status,
        session_type=session_type,
        date_from=date_from,
        date_to=date_to,
        q=q,
    )

    page_obj, page_numbers, per_page_param, total_count = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="10",
    )
    pagination_qs = build_pagination_query_string(
        bucket=bucket,
        status=status,
        session_type=session_type,
        date_from=date_from,
        date_to=date_to,
        q=q,
        per_page=per_page_param,
    )
    hidden_fields = []
    for name, value, skip in (
        ("bucket", bucket, "all"),
        ("status", status, "all"),
        ("session_type", session_type, "all"),
        ("date_from", date_from, ""),
        ("date_to", date_to, ""),
        ("q", q, ""),
    ):
        if value and value != skip:
            hidden_fields.append({"name": name, "value": value})

    return render(
        request,
        "dashboard/pages/appointments/all_list.html",
        {
            "active_tab": "all",
            "appointments": page_obj.object_list,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_count": total_count,
            "bucket": bucket,
            "status_filter": status,
            "session_type_filter": session_type,
            "date_from": date_from,
            "date_to": date_to,
            "q": q,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
            "status_choices": AppointmentStatus.choices,
            "session_type_choices": SessionType.choices,
            "status_labels": _status_badge_map(),
        },
    )


@login_required
@permissions_required(*_VIEW_ALL)
@require_GET
def appointment_detail(request, pk):
    appointment = _require_appointment(request.user, pk)
    history = list(
        appointment.status_history.select_related("changed_by").order_by(
            "-created_at", "-id"
        )
    )
    return render(
        request,
        "dashboard/pages/appointments/detail.html",
        {
            "active_tab": "all",
            "appointment": appointment,
            "history": history,
            "status_labels": _status_badge_map(),
            "session_type_labels": dict(SessionType.choices),
        },
    )
