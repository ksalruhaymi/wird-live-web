import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.subscription.services import CALL_INELIGIBLE_MESSAGE
from apps.calls.exceptions import CallProviderError, CallValidationError
from apps.calls.models import CallSession
from apps.calls.services import (
    accept_call_session,
    call_to_payload,
    cancel_pending_call,
    end_call_session,
    get_call_for_user,
    list_incoming_calls,
    reject_call_session,
    request_call_session,
    resolve_user_type_slug,
)


def _require_auth(request) -> JsonResponse | None:
    if request.user.is_authenticated:
        return None
    return JsonResponse(
        {"success": False, "message": "يجب تسجيل الدخول."},
        status=401,
    )


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _parse_teacher_id(data: dict) -> int | None:
    raw = data.get("teacher_id")
    if raw is None:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _handle_call_error(exc) -> JsonResponse:
    if isinstance(exc, CallValidationError):
        status = 400
        if exc.message == CALL_INELIGIBLE_MESSAGE or "اشتراك" in exc.message:
            status = 403
        return JsonResponse({"success": False, "message": exc.message}, status=status)
    if isinstance(exc, CallProviderError):
        return JsonResponse({"success": False, "message": exc.message}, status=503)
    return JsonResponse({"success": False, "message": "خطأ غير متوقع."}, status=500)


@csrf_exempt
@require_POST
def request_call(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    from apps.tutoring.teacher_services import resolve_user_type_slug

    if resolve_user_type_slug(request.user) == "teacher":
        return JsonResponse(
            {
                "success": False,
                "message": "المعلّم يستقبل الاتصالات فقط ولا يمكنه بدء اتصال.",
            },
            status=403,
        )

    data = _parse_json_body(request)
    teacher_id = _parse_teacher_id(data)
    session_type = (data.get("session_type") or "").strip().lower()

    if not teacher_id:
        return JsonResponse(
            {"success": False, "message": "يجب اختيار معلّم."},
            status=400,
        )
    if session_type not in CallSession.SessionType.values:
        return JsonResponse(
            {"success": False, "message": "نوع الاتصال غير صالح."},
            status=400,
        )

    try:
        call = request_call_session(
            request.user,
            session_type=session_type,
            teacher_id=teacher_id,
        )
    except (CallValidationError, CallProviderError) as exc:
        return _handle_call_error(exc)

    return JsonResponse(
        {"success": True, "call": call_to_payload(call, request.user, request)},
        status=201,
    )


@csrf_exempt
@require_GET
def incoming_calls(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    if resolve_user_type_slug(request.user) != "teacher":
        return JsonResponse(
            {"success": False, "message": "هذا المسار للمعلّمين فقط."},
            status=403,
        )

    calls = list_incoming_calls(request.user)
    return JsonResponse(
        {
            "success": True,
            "calls": [call_to_payload(c, request.user, request) for c in calls],
        }
    )


@csrf_exempt
@require_GET
def call_detail(request, pk):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    call, error = get_call_for_user(pk, request.user)
    if error:
        status = 404 if error == "المكالمة غير موجودة." else 403
        return JsonResponse({"success": False, "message": error}, status=status)

    return JsonResponse(
        {"success": True, "call": call_to_payload(call, request.user, request)}
    )


@csrf_exempt
@require_POST
def accept_call(request, pk):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    call = get_object_or_404(
        CallSession.objects.select_related("student", "teacher"),
        pk=pk,
    )
    updated, error = accept_call_session(call, request.user)
    if error:
        status = 403 if "غير مصرح" in error or "للمعلّمين" in error else 400
        return JsonResponse({"success": False, "message": error}, status=status)

    try:
        payload = call_to_payload(updated, request.user, request)
    except CallProviderError as exc:
        return _handle_call_error(exc)

    return JsonResponse({"success": True, "call": payload})


@csrf_exempt
@require_POST
def reject_call(request, pk):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    call = get_object_or_404(
        CallSession.objects.select_related("student", "teacher"),
        pk=pk,
    )
    updated, error = reject_call_session(call, request.user)
    if error:
        status = 403 if "غير مصرح" in error else 400
        return JsonResponse({"success": False, "message": error}, status=status)

    return JsonResponse(
        {"success": True, "call": call_to_payload(updated, request.user, request)}
    )


@csrf_exempt
@require_POST
def cancel_call(request, pk):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    call = get_object_or_404(
        CallSession.objects.select_related("student", "teacher"),
        pk=pk,
    )
    updated, error = cancel_pending_call(call, request.user)
    if error:
        status = 403 if "غير مصرح" in error else 400
        return JsonResponse({"success": False, "message": error}, status=status)

    return JsonResponse(
        {"success": True, "call": call_to_payload(updated, request.user, request)}
    )


@csrf_exempt
@require_POST
def end_call(request, pk):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    call = get_object_or_404(
        CallSession.objects.select_related("student", "teacher"),
        pk=pk,
    )
    updated, error = end_call_session(call, request.user)
    if error:
        return JsonResponse({"success": False, "message": error}, status=403)

    recording_status = ""
    recording_pending = bool(getattr(updated, "_recording_pending", False))
    try:
        rec = updated.recording
        recording_status = rec.recording_status or ""
        recording_pending = recording_pending or rec.is_preparing
    except Exception:
        pass

    payload = call_to_payload(updated, request.user, request)
    return JsonResponse(
        {
            "success": True,
            "call": payload,
            "call_status": updated.status,
            "recording_status": recording_status,
            "recording_pending": recording_pending,
            "message": (
                "تم إنهاء المكالمة، ويجري تجهيز التسجيل في الخلفية."
                if recording_pending
                else "تم إنهاء المكالمة."
            ),
        }
    )


def _request_call_with_type(request, session_type: str):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    from apps.tutoring.teacher_services import resolve_user_type_slug

    if resolve_user_type_slug(request.user) == "teacher":
        return JsonResponse(
            {
                "success": False,
                "message": "المعلّم يستقبل الاتصالات فقط ولا يمكنه بدء اتصال.",
            },
            status=403,
        )

    teacher_id = _parse_teacher_id(_parse_json_body(request))
    if not teacher_id:
        return JsonResponse(
            {"success": False, "message": "يجب اختيار معلّم."},
            status=400,
        )

    try:
        call = request_call_session(
            request.user,
            session_type=session_type,
            teacher_id=teacher_id,
        )
    except (CallValidationError, CallProviderError) as exc:
        return _handle_call_error(exc)

    return JsonResponse(
        {"success": True, "call": call_to_payload(call, request.user, request)},
        status=201,
    )


@csrf_exempt
@require_POST
def start_audio(request):
    return _request_call_with_type(request, CallSession.SessionType.AUDIO)


@csrf_exempt
@require_POST
def start_video(request):
    return _request_call_with_type(request, CallSession.SessionType.VIDEO)


@csrf_exempt
@require_GET
def my_calls(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    calls = (
        CallSession.objects.filter(student=request.user)
        .select_related("teacher", "student")
        .order_by("-created_at", "-id")
    )
    return JsonResponse(
        {
            "success": True,
            "calls": [call_to_payload(c, request.user, request) for c in calls],
        }
    )
