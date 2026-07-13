from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.appointments.access import (
    appointments_queryset_for,
    exceptions_queryset_for,
    get_appointment_for_user,
    rules_queryset_for,
    schedule_owner,
    user_can_manage_bookings,
    user_can_manage_schedule,
    user_can_override_status,
    user_can_view_all_appointments,
)
from apps.appointments.exceptions import AppointmentError
from apps.appointments.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentSlot,
    AppointmentStatus,
    SessionType,
    SlotStatus,
)
from apps.appointments.services import (
    add_availability_exception,
    cancel_by_teacher,
    create_availability_rule,
    deactivate_availability_rule,
    get_or_create_booking_settings,
    mark_appointment_status,
    nearest_available_slot,
    preview_availability_exception,
    start_appointment_call,
    update_booking_settings,
)
from apps.calls.models import CallSession
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from dashboard.forms.appointments import (
    AppointmentCancelForm,
    AppointmentStatusForm,
    AvailabilityRuleForm,
    BookingSettingsForm,
    ExceptionForm,
)
from identity.accounts.user_types import USER_TYPE_TEACHER
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


def _toast_success(request, message: str) -> None:
    messages.success(request, message, extra_tags="toast")


def _toast_error(request, message: str) -> None:
    messages.error(request, message, extra_tags="toast")


def _require_appointment(user, pk: int) -> Appointment:
    appointment = get_appointment_for_user(user, pk)
    if appointment is None:
        raise Http404
    return appointment


def _apply_booking_filters(qs, *, bucket, status, session_type, date_from, date_to, q, search_teacher=False):
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
        )
        if search_teacher:
            name_q |= (
                Q(teacher__full_name__icontains=q)
                | Q(teacher__username__icontains=q)
                | Q(teacher__teacher_profile__display_name__icontains=q)
            )
        if q.isdigit():
            name_q |= Q(pk=int(q))
        qs = qs.filter(name_q)
    return qs


def _status_badge_map():
    return {value: label for value, label in AppointmentStatus.choices}


@login_required
@permissions_required("dashboard.access", "appointments.view")
def appointment_overview(request):
    user = request.user
    now = timezone.now()
    today = timezone.localdate()
    week_end = now + timedelta(days=7)

    qs = appointments_queryset_for(user)
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

    slots_qs = AppointmentSlot.objects.filter(
        status=SlotStatus.AVAILABLE,
        start_at__gte=now,
        start_at__lte=week_end,
    )
    if not user_can_view_all_appointments(user):
        slots_qs = slots_qs.filter(teacher=user)
    available_slots_7d = slots_qs.count()

    settings_obj = None
    nearest = None
    booking_enabled = None
    if not user_can_view_all_appointments(user) or getattr(user, "user_type", None) == USER_TYPE_TEACHER:
        settings_obj = get_or_create_booking_settings(user)
        booking_enabled = settings_obj.booking_enabled
        nearest = nearest_available_slot(user) if booking_enabled else None

    upcoming_preview = list(
        qs.filter(status__in=ACTIVE_APPOINTMENT_STATUSES, slot__start_at__gte=now)
        .order_by("slot__start_at", "id")[:5]
    )

    return render(
        request,
        "dashboard/pages/appointments/overview.html",
        {
            "active_tab": "overview",
            "stats": stats,
            "available_slots_7d": available_slots_7d,
            "nearest": nearest,
            "booking_enabled": booking_enabled,
            "upcoming_preview": upcoming_preview,
            "can_view_all": user_can_view_all_appointments(user),
            "can_manage_schedule": user_can_manage_schedule(user),
            "can_manage_bookings": user_can_manage_bookings(user),
            "status_labels": _status_badge_map(),
        },
    )


@login_required
@permissions_required("dashboard.access", "appointments.view")
def appointment_booking_list(request):
    bucket = (request.GET.get("bucket") or "upcoming").strip()
    status = (request.GET.get("status") or "all").strip()
    session_type = (request.GET.get("session_type") or "all").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    q = (request.GET.get("q") or "").strip()

    qs = _apply_booking_filters(
        appointments_queryset_for(request.user).order_by("slot__start_at", "id"),
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
        ("bucket", bucket, "upcoming"),
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
        "dashboard/pages/appointments/bookings.html",
        {
            "active_tab": "bookings",
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
            "can_view_all": user_can_view_all_appointments(request.user),
            "can_manage_bookings": user_can_manage_bookings(request.user),
            "status_labels": _status_badge_map(),
        },
    )


@login_required
@permissions_required("dashboard.access", "appointments.view")
def appointment_detail(request, pk):
    appointment = _require_appointment(request.user, pk)
    history = list(
        appointment.status_history.select_related("changed_by").order_by("-created_at", "-id")
    )
    can_manage = user_can_manage_bookings(request.user) and appointment.teacher_id == request.user.id
    can_override = user_can_override_status(request.user) and appointment.teacher_id == request.user.id
    can_start = can_manage and appointment.status in {
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.IN_PROGRESS,
    }
    return render(
        request,
        "dashboard/pages/appointments/detail.html",
        {
            "active_tab": "bookings",
            "appointment": appointment,
            "history": history,
            "cancel_form": AppointmentCancelForm(),
            "status_form": AppointmentStatusForm(),
            "can_manage_bookings": can_manage,
            "can_override_status": can_override or can_manage,
            "can_start_call": can_start,
            "can_view_all": user_can_view_all_appointments(request.user),
            "status_labels": _status_badge_map(),
            "session_type_labels": dict(SessionType.choices),
        },
    )


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.manage_bookings")
@require_POST
def appointment_cancel(request, pk):
    appointment = _require_appointment(request.user, pk)
    if appointment.teacher_id != request.user.id:
        raise Http404
    form = AppointmentCancelForm(request.POST)
    if not form.is_valid():
        _toast_error(request, "بيانات الإلغاء غير صالحة.")
        return redirect("dashboard:appointment_detail", pk=pk)
    try:
        cancel_by_teacher(
            appointment.pk,
            request.user,
            reason=form.cleaned_data.get("reason") or "",
            reopen_slot=bool(form.cleaned_data.get("reopen_slot")),
        )
        _toast_success(request, "تم إلغاء الموعد.")
    except AppointmentError as exc:
        _toast_error(request, exc.message)
    return redirect("dashboard:appointment_detail", pk=pk)


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.manage_bookings")
@require_POST
def appointment_mark_status(request, pk):
    appointment = _require_appointment(request.user, pk)
    if appointment.teacher_id != request.user.id:
        raise Http404
    form = AppointmentStatusForm(request.POST)
    if not form.is_valid():
        _toast_error(request, "الحالة غير صالحة.")
        return redirect("dashboard:appointment_detail", pk=pk)
    try:
        mark_appointment_status(
            appointment.pk,
            request.user,
            new_status=form.cleaned_data["status"],
        )
        _toast_success(request, "تم تحديث حالة الموعد.")
    except AppointmentError as exc:
        _toast_error(request, exc.message)
    return redirect("dashboard:appointment_detail", pk=pk)


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.manage_bookings")
@require_POST
def appointment_start_call(request, pk):
    appointment = _require_appointment(request.user, pk)
    if appointment.teacher_id != request.user.id:
        raise Http404
    try:
        _, call = start_appointment_call(
            request.user,
            appointment.pk,
            session_type=CallSession.SessionType.AUDIO,
        )
        _toast_success(request, "تم بدء المكالمة.")
        return redirect("dashboard:call_session_detail", session_id=call.id)
    except AppointmentError as exc:
        _toast_error(request, exc.message)
        return redirect("dashboard:appointment_detail", pk=pk)


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.manage_schedule")
def appointment_schedule_list(request):
    teacher = schedule_owner(request.user)
    rules = list(rules_queryset_for(teacher).order_by("-is_active", "start_date", "start_time"))
    now = timezone.now()
    upcoming_slots = list(
        AppointmentSlot.objects.filter(
            teacher=teacher,
            status=SlotStatus.AVAILABLE,
            start_at__gte=now,
            start_at__lte=now + timedelta(days=7),
        ).order_by("start_at", "id")[:40]
    )
    return render(
        request,
        "dashboard/pages/appointments/schedule.html",
        {
            "active_tab": "schedule",
            "rules": rules,
            "upcoming_slots": upcoming_slots,
            "can_view_all": user_can_view_all_appointments(request.user),
            "can_manage_schedule": True,
        },
    )


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.manage_schedule")
def appointment_rule_create(request):
    teacher = schedule_owner(request.user)
    form = AvailabilityRuleForm(
        request.POST or None,
        initial={
            "start_date": timezone.localdate(),
            "recurrence_type": "none",
            "slot_duration_minutes": 30,
            "break_minutes": 5,
        },
    )
    if request.method == "POST" and form.is_valid():
        try:
            create_availability_rule(teacher, form.to_service_data())
            _toast_success(request, "تم إنشاء قاعدة التوفر.")
            return redirect("dashboard:appointment_schedule_list")
        except AppointmentError as exc:
            _toast_error(request, exc.message)
    return render(
        request,
        "dashboard/pages/appointments/rule_create.html",
        {
            "active_tab": "schedule",
            "form": form,
            "can_view_all": user_can_view_all_appointments(request.user),
        },
    )


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.manage_schedule")
@require_POST
def appointment_rule_deactivate(request, pk):
    teacher = schedule_owner(request.user)
    try:
        deactivate_availability_rule(teacher, pk)
        _toast_success(request, "تم تعطيل القاعدة.")
    except AppointmentError as exc:
        _toast_error(request, exc.message)
    return redirect("dashboard:appointment_schedule_list")


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.manage_schedule")
def appointment_exceptions(request):
    teacher = schedule_owner(request.user)
    exceptions = list(exceptions_queryset_for(teacher).order_by("-date", "-id")[:100])
    form = ExceptionForm(request.POST or None)
    preview = None
    show_confirm = False

    if request.method == "POST" and form.is_valid():
        data = form.to_service_data()
        confirm_cancel = request.POST.get("confirm_cancel") == "1"
        try:
            preview = preview_availability_exception(teacher, data)
            if preview["affected_count"] > 0 and not confirm_cancel:
                show_confirm = True
            else:
                add_availability_exception(
                    teacher,
                    data,
                    cancel_affected_bookings=preview["affected_count"] > 0,
                    cancellation_reason=form.cleaned_data.get("cancellation_reason")
                    or form.cleaned_data.get("reason")
                    or "",
                )
                _toast_success(request, "تم إضافة الاستثناء.")
                return redirect("dashboard:appointment_exceptions")
        except AppointmentError as exc:
            _toast_error(request, exc.message)

    return render(
        request,
        "dashboard/pages/appointments/exceptions.html",
        {
            "active_tab": "exceptions",
            "exceptions": exceptions,
            "form": form,
            "preview": preview,
            "show_confirm": show_confirm,
            "can_view_all": user_can_view_all_appointments(request.user),
        },
    )


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.manage_schedule")
def appointment_settings(request):
    teacher = schedule_owner(request.user)
    settings_obj = get_or_create_booking_settings(teacher)
    initial = {
        "booking_enabled": settings_obj.booking_enabled,
        "default_slot_duration_minutes": settings_obj.default_slot_duration_minutes,
        "default_break_minutes": settings_obj.default_break_minutes,
        "minimum_booking_notice_minutes": settings_obj.minimum_booking_notice_minutes,
        "maximum_booking_window_days": settings_obj.maximum_booking_window_days,
        "cancellation_deadline_minutes": settings_obj.cancellation_deadline_minutes,
        "max_active_bookings_per_student": settings_obj.max_active_bookings_per_student,
        "timezone": settings_obj.timezone,
        "allowed_session_types": settings_obj.allowed_session_types or [],
    }
    form = BookingSettingsForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        update_booking_settings(teacher, **form.to_service_kwargs())
        _toast_success(request, "تم حفظ إعدادات الحجز.")
        return redirect("dashboard:appointment_settings")
    return render(
        request,
        "dashboard/pages/appointments/settings.html",
        {
            "active_tab": "settings",
            "form": form,
            "settings_obj": settings_obj,
            "can_view_all": user_can_view_all_appointments(request.user),
        },
    )


@login_required
@permissions_required("dashboard.access", "appointments.view", "appointments.view_all")
def appointment_all_list(request):
    bucket = (request.GET.get("bucket") or "all").strip()
    status = (request.GET.get("status") or "all").strip()
    session_type = (request.GET.get("session_type") or "all").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()
    q = (request.GET.get("q") or "").strip()

    qs = _apply_booking_filters(
        appointments_queryset_for(request.user).order_by("-slot__start_at", "-id"),
        bucket=bucket if bucket != "all" else "",
        status=status,
        session_type=session_type,
        date_from=date_from,
        date_to=date_to,
        q=q,
        search_teacher=True,
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
            "can_view_all": True,
            "status_labels": _status_badge_map(),
        },
    )
