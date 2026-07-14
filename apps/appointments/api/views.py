import json
from datetime import date

from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.appointments.exceptions import AppointmentError
from apps.appointments.models import Appointment, AvailabilityRule
from apps.appointments.services import (
    add_availability_exception,
    appointment_to_payload,
    available_days,
    available_slots_for_day,
    book_slot,
    cancel_available_slot,
    cancel_by_student,
    cancel_by_teacher,
    clear_day_available_slots,
    create_availability_for_dates,
    create_availability_rule,
    deactivate_availability_rule,
    get_or_create_booking_settings,
    mark_appointment_status,
    nearest_available_slot,
    preview_availability_exception,
    rule_to_payload,
    session_types_payload,
    settings_to_payload,
    slot_to_payload,
    start_appointment_call,
    student_appointments,
    student_calendar_month,
    teacher_appointments,
    teacher_availability_summary,
    teacher_calendar_month,
    teacher_day_schedule,
    upcoming_count_for_student,
    update_booking_settings,
)
from apps.calls.services import call_to_payload
from identity.accounts.user_types import resolve_user_type_slug

User = get_user_model()


def _require_auth(request):
    if request.user.is_authenticated:
        return None
    return JsonResponse({"success": False, "message": "يجب تسجيل الدخول."}, status=401)


def _parse_json(request) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _error(exc: AppointmentError) -> JsonResponse:
    return JsonResponse(
        {"success": False, "message": exc.message, "code": exc.code},
        status=exc.status,
    )


def _require_teacher(request):
    err = _require_auth(request)
    if err:
        return err, None
    if resolve_user_type_slug(request.user) != "teacher":
        return (
            JsonResponse(
                {"success": False, "message": "هذا الإجراء للمعلمين فقط.", "code": "forbidden"},
                status=403,
            ),
            None,
        )
    return None, request.user


def _paginate(qs, request, *, default_limit=20):
    try:
        page = max(int(request.GET.get("page") or 1), 1)
    except (TypeError, ValueError):
        page = 1
    try:
        limit = min(max(int(request.GET.get("limit") or default_limit), 1), 100)
    except (TypeError, ValueError):
        limit = default_limit
    offset = (page - 1) * limit
    total = qs.count()
    items = list(qs[offset : offset + limit])
    return items, {"page": page, "limit": limit, "total": total}


def _parse_day(raw) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Shared / student
# ---------------------------------------------------------------------------


@require_GET
def session_types(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    return JsonResponse({"success": True, "session_types": session_types_payload()})


@require_GET
def teacher_summary(request, teacher_id: int):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    teacher = get_object_or_404(User, pk=teacher_id, teacher_profile__isnull=False)
    summary = teacher_availability_summary(teacher)
    settings_obj = get_or_create_booking_settings(teacher)
    message = ""
    if not settings_obj.booking_enabled:
        message = "المعلم لا يستقبل حجوزات جديدة حاليًا"
    elif not summary["has_available_slots"]:
        message = "لا توجد مواعيد متاحة حاليًا"
    return JsonResponse(
        {
            "success": True,
            **summary,
            "settings": settings_to_payload(settings_obj),
            "message": message,
            "days": available_days(teacher, days=30) if settings_obj.booking_enabled else [],
        }
    )


@require_GET
def teacher_days(request, teacher_id: int):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    teacher = get_object_or_404(User, pk=teacher_id, teacher_profile__isnull=False)
    from_date = _parse_day(request.GET.get("from"))
    raw = request.GET.get("days")
    if raw is None:
        days = 30
    else:
        try:
            raw_days = int(raw)
        except (TypeError, ValueError):
            return JsonResponse(
                {
                    "success": False,
                    "message": "قيمة days غير صالحة.",
                    "code": "invalid_days",
                },
                status=400,
            )
        if raw_days > 90:
            return JsonResponse(
                {
                    "success": False,
                    "message": "الحد الأقصى لنطاق الأيام هو 90 يومًا.",
                    "code": "days_limit",
                },
                status=400,
            )
        days = min(max(raw_days, 1), 90)
    return JsonResponse(
        {
            "success": True,
            "teacher_id": teacher_id,
            "days": available_days(teacher, from_date=from_date, days=days),
        }
    )


@require_GET
def teacher_day_slots(request, teacher_id: int):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    teacher = get_object_or_404(User, pk=teacher_id, teacher_profile__isnull=False)
    day = _parse_day(request.GET.get("date"))
    if not day:
        return JsonResponse(
            {"success": False, "message": "التاريخ مطلوب.", "code": "date_required"},
            status=400,
        )
    slots = available_slots_for_day(teacher, day)
    return JsonResponse(
        {
            "success": True,
            "teacher_id": teacher_id,
            "date": day.isoformat(),
            "slots": [slot_to_payload(s) for s in slots],
        }
    )


@require_GET
def student_teacher_calendar(request, teacher_id: int):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    teacher = get_object_or_404(User, pk=teacher_id, teacher_profile__isnull=False)
    try:
        payload = student_calendar_month(teacher, month=request.GET.get("month"))
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse({"success": True, "teacher_id": teacher_id, **payload})


# ---------------------------------------------------------------------------
# Teacher calendar / simple availability
# ---------------------------------------------------------------------------


@require_GET
def teacher_own_calendar(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    try:
        payload = teacher_calendar_month(teacher, month=request.GET.get("month"))
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse({"success": True, **payload})


@require_GET
def teacher_own_day(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    day = _parse_day(request.GET.get("date"))
    if not day:
        return JsonResponse(
            {"success": False, "message": "التاريخ مطلوب.", "code": "date_required"},
            status=400,
        )
    payload = teacher_day_schedule(teacher, day, request=request)
    return JsonResponse({"success": True, **payload})


@csrf_exempt
@require_POST
def teacher_create_availability(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    data = _parse_json(request)
    try:
        rules = create_availability_for_dates(teacher, data)
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "success": True,
            "message": "تم إضافة الأوقات المتاحة.",
            "rules": [rule_to_payload(r) for r in rules],
            "created_count": len(rules),
        },
        status=201,
    )


@csrf_exempt
@require_POST
def teacher_cancel_slot(request, slot_id: int):
    err, teacher = _require_teacher(request)
    if err:
        return err
    try:
        slot = cancel_available_slot(teacher, slot_id)
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "success": True,
            "message": "تم حذف الفترة المتاحة.",
            "slot": slot_to_payload(slot),
        }
    )


@csrf_exempt
@require_POST
def teacher_clear_day(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    data = _parse_json(request)
    day = _parse_day(data.get("date") or request.GET.get("date"))
    if not day:
        return JsonResponse(
            {"success": False, "message": "التاريخ مطلوب.", "code": "date_required"},
            status=400,
        )
    try:
        cleared = clear_day_available_slots(teacher, day)
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "success": True,
            "message": "تم حذف الأوقات غير المحجوزة لهذا اليوم.",
            "date": day.isoformat(),
            "cleared_count": cleared,
        }
    )


@csrf_exempt
@require_POST
def book(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    data = _parse_json(request)
    try:
        slot_id = int(data.get("slot_id"))
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "slot_id مطلوب.", "code": "slot_required"},
            status=400,
        )
    try:
        appointment = book_slot(
            student=request.user,
            slot_id=slot_id,
            session_type=data.get("session_type") or "",
            session_type_other=data.get("session_type_other") or "",
            student_notes=data.get("student_notes") or "",
        )
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "success": True,
            "message": "تم حجز موعدك بنجاح.",
            "appointment": appointment_to_payload(
                appointment, viewer=request.user, request=request
            ),
        },
        status=201,
    )


@require_GET
def my_appointments(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    bucket = (request.GET.get("bucket") or "upcoming").strip()
    qs = student_appointments(request.user, bucket=bucket)
    items, pagination = _paginate(qs, request)
    return JsonResponse(
        {
            "success": True,
            "bucket": bucket,
            "appointments": [
                appointment_to_payload(a, viewer=request.user, request=request)
                for a in items
            ],
            "pagination": pagination,
            "upcoming_count": upcoming_count_for_student(request.user),
        }
    )


@require_GET
def my_upcoming_count(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    return JsonResponse(
        {
            "success": True,
            "upcoming_count": upcoming_count_for_student(request.user),
        }
    )


@require_GET
def appointment_detail(request, pk: int):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    appointment = get_object_or_404(
        Appointment.objects.select_related(
            "slot", "teacher", "student", "call_session"
        ),
        pk=pk,
    )
    if request.user.id not in {appointment.student_id, appointment.teacher_id}:
        slug = resolve_user_type_slug(request.user)
        if slug not in {"admin", "supervisor"}:
            return JsonResponse(
                {"success": False, "message": "غير مصرح.", "code": "forbidden"},
                status=403,
            )
    return JsonResponse(
        {
            "success": True,
            "appointment": appointment_to_payload(
                appointment, viewer=request.user, request=request
            ),
        }
    )


@csrf_exempt
@require_POST
def cancel_appointment(request, pk: int):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    data = _parse_json(request)
    reason = data.get("reason") or ""
    slug = resolve_user_type_slug(request.user)
    try:
        if slug == "teacher":
            appointment = cancel_by_teacher(
                pk,
                request.user,
                reason=reason,
                reopen_slot=bool(data.get("reopen_slot")),
            )
        else:
            appointment = cancel_by_student(pk, request.user, reason=reason)
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "success": True,
            "message": "تم إلغاء الموعد.",
            "appointment": appointment_to_payload(
                appointment, viewer=request.user, request=request
            ),
        }
    )


@csrf_exempt
@require_POST
def start_call(request, pk: int):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    data = _parse_json(request)
    try:
        appointment, call = start_appointment_call(
            request.user,
            pk,
            session_type=data.get("session_type") or "audio",
        )
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "success": True,
            "appointment": appointment_to_payload(
                appointment, viewer=request.user, request=request
            ),
            "call": call_to_payload(call, viewer=request.user, request=request),
        }
    )


# ---------------------------------------------------------------------------
# Teacher
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "PATCH", "PUT"])
@csrf_exempt
def teacher_settings(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    if request.method == "GET":
        settings_obj = get_or_create_booking_settings(teacher)
        return JsonResponse(
            {"success": True, "settings": settings_to_payload(settings_obj)}
        )

    data = _parse_json(request)
    allowed_fields = {}
    for key in (
        "booking_enabled",
        "approval_required",
        "default_slot_duration_minutes",
        "default_break_minutes",
        "minimum_booking_notice_minutes",
        "maximum_booking_window_days",
        "cancellation_deadline_minutes",
        "max_active_bookings_per_student",
        "allowed_session_types",
        "timezone",
    ):
        if key in data:
            allowed_fields[key] = data[key]
    settings_obj = update_booking_settings(teacher, **allowed_fields)
    return JsonResponse(
        {"success": True, "settings": settings_to_payload(settings_obj)}
    )


@csrf_exempt
@require_POST
def teacher_toggle_booking(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    data = _parse_json(request)
    enabled = data.get("booking_enabled")
    if enabled is None:
        settings_obj = get_or_create_booking_settings(teacher)
        enabled = not settings_obj.booking_enabled
    settings_obj = update_booking_settings(teacher, booking_enabled=bool(enabled))
    return JsonResponse(
        {"success": True, "settings": settings_to_payload(settings_obj)}
    )


@require_GET
def teacher_bookings(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    bucket = (request.GET.get("bucket") or "upcoming").strip()
    qs = teacher_appointments(teacher, bucket=bucket)
    items, pagination = _paginate(qs, request)
    return JsonResponse(
        {
            "success": True,
            "bucket": bucket,
            "appointments": [
                appointment_to_payload(a, viewer=request.user, request=request)
                for a in items
            ],
            "pagination": pagination,
        }
    )


@require_GET
def teacher_rules(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    rules = AvailabilityRule.objects.filter(teacher=teacher).order_by("-id")
    return JsonResponse(
        {"success": True, "rules": [rule_to_payload(r) for r in rules]}
    )


@csrf_exempt
@require_POST
def teacher_create_rule(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    data = _parse_json(request)
    try:
        rule = create_availability_rule(teacher, data)
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse(
        {"success": True, "rule": rule_to_payload(rule)},
        status=201,
    )


@csrf_exempt
@require_POST
def teacher_deactivate_rule(request, rule_id: int):
    err, teacher = _require_teacher(request)
    if err:
        return err
    data = _parse_json(request)
    try:
        rule = deactivate_availability_rule(
            teacher,
            rule_id,
            future_only=bool(data.get("future_only", True)),
        )
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse({"success": True, "rule": rule_to_payload(rule)})


@csrf_exempt
@require_POST
def teacher_preview_exception(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    data = _parse_json(request)
    try:
        preview = preview_availability_exception(teacher, data)
    except AppointmentError as e:
        return _error(e)
    return JsonResponse({"success": True, **preview})


@csrf_exempt
@require_POST
def teacher_add_exception(request):
    err, teacher = _require_teacher(request)
    if err:
        return err
    data = _parse_json(request)
    try:
        exc = add_availability_exception(
            teacher,
            data,
            cancel_affected_bookings=bool(data.get("cancel_affected_bookings")),
            cancellation_reason=data.get("cancellation_reason") or "",
        )
    except AppointmentError as e:
        return _error(e)
    return JsonResponse(
        {
            "success": True,
            "exception": {
                "id": exc.id,
                "date": exc.date.isoformat(),
                "exception_type": exc.exception_type,
                "start_time": exc.start_time.strftime("%H:%M") if exc.start_time else None,
                "end_time": exc.end_time.strftime("%H:%M") if exc.end_time else None,
                "reason": exc.reason,
            },
        },
        status=201,
    )


@csrf_exempt
@require_POST
def teacher_mark_status(request, pk: int):
    err, teacher = _require_teacher(request)
    if err:
        return err
    data = _parse_json(request)
    try:
        appointment = mark_appointment_status(
            pk,
            teacher,
            new_status=(data.get("status") or "").strip(),
            note=data.get("note") or "",
        )
    except AppointmentError as exc:
        return _error(exc)
    return JsonResponse(
        {
            "success": True,
            "appointment": appointment_to_payload(
                appointment, viewer=request.user, request=request
            ),
        }
    )


@require_GET
def teacher_nearest_self(request):
    """Debug/helper: nearest slot for the authenticated teacher."""
    err, teacher = _require_teacher(request)
    if err:
        return err
    slot = nearest_available_slot(teacher)
    return JsonResponse(
        {
            "success": True,
            "nearest_slot": slot_to_payload(slot) if slot else None,
        }
    )
