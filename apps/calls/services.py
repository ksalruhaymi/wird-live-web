from django.conf import settings
from django.utils import timezone

from apps.maqraa.teacher_services import (
    get_teacher_user,
    mark_teacher_busy,
    mark_teacher_online,
    teacher_display_name,
    validate_teacher_for_call,
)
from apps.subscription.services import student_can_request_call
from identity.accounts.auth.profile_service import _resolve_profile_image_url
from identity.accounts.user_types import resolve_user_type_slug

from .exceptions import CallProviderError, CallValidationError
from .models import CallSession
from .token_builder import (
    assign_channel_name,
    build_token_for_uid,
    ensure_agora_provider,
    provider_name_for_new_call,
    token_expiry_iso,
    uses_agora_rtc,
)


def student_display_name(user) -> str:
    profile = getattr(user, "student_profile", None)
    if profile and profile.display_name:
        return profile.display_name
    full = (getattr(user, "full_name", "") or "").strip()
    return full or user.username


def _can_view_call(call: CallSession, user) -> bool:
    return user.id in {call.student_id, call.teacher_id}


def call_to_payload(call: CallSession, viewer=None, request=None) -> dict:
    ensure_agora_provider(call)

    app_id = ""
    if uses_agora_rtc(call):
        app_id = (getattr(settings, "AGORA_APP_ID", "") or "").strip()

    teacher_name = ""
    if call.teacher_id and call.teacher:
        teacher_name = teacher_display_name(call.teacher)

    student_name = ""
    student_profile_image_url = ""
    if call.student:
        student_name = student_display_name(call.student)
        student_profile_image_url = (
            _resolve_profile_image_url(call.student, request) or ""
        )

    teacher_profile_image_url = ""
    if call.teacher_id and call.teacher:
        teacher_profile_image_url = (
            _resolve_profile_image_url(call.teacher, request) or ""
        )

    payload = {
        "id": call.id,
        "session_type": call.session_type,
        "provider": call.provider,
        "app_id": app_id,
        "channel_name": call.channel_name or "",
        "room_name": call.room_name or "",
        "token": "",
        "uid": call.student_id,
        "teacher_id": call.teacher_id,
        "teacher_name": teacher_name,
        "teacher_profile_image_url": teacher_profile_image_url,
        "student_name": student_name,
        "student_profile_image_url": student_profile_image_url,
        "status": call.status,
        "created_at": call.created_at.isoformat() if call.created_at else None,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
    }

    if (
        viewer is not None
        and call.status == CallSession.Status.ACTIVE
        and _can_view_call(call, viewer)
    ):
        payload["uid"] = viewer.id
        payload["token"] = build_token_for_uid(call, viewer.id)
        if uses_agora_rtc(call):
            payload["token_expires_at"] = token_expiry_iso()

    return payload


def request_call_session(
    user,
    *,
    session_type: str,
    teacher_id: int,
) -> CallSession:
    if resolve_user_type_slug(user) == "teacher":
        raise CallValidationError("المعلّم لا يمكنه طلب اتصال بمعلّم آخر.")

    can_call, eligibility_message = student_can_request_call(user)
    if not can_call:
        raise CallValidationError(eligibility_message)

    if not teacher_id:
        raise CallValidationError("يجب اختيار معلّم.")

    teacher = get_teacher_user(teacher_id)
    if teacher is None:
        raise CallValidationError("المعلّم غير موجود أو غير معتمد.")

    validation_error = validate_teacher_for_call(teacher, session_type=session_type)
    if validation_error:
        raise CallValidationError(validation_error)

    call = CallSession.objects.create(
        student=user,
        teacher=teacher,
        session_type=session_type,
        provider=provider_name_for_new_call(),
        status=CallSession.Status.PENDING,
    )
    assign_channel_name(call)
    mark_teacher_busy(teacher)
    return call


def list_incoming_calls(teacher_user) -> list[CallSession]:
    return list(
        CallSession.objects.filter(
            teacher=teacher_user,
            status__in=[
                CallSession.Status.PENDING,
                CallSession.Status.ACTIVE,
            ],
        )
        .select_related("student", "teacher")
        .order_by("-created_at", "-id")
    )


def get_call_for_user(call_id: int, user) -> tuple[CallSession | None, str | None]:
    try:
        call = CallSession.objects.select_related("student", "teacher").get(pk=call_id)
    except CallSession.DoesNotExist:
        return None, "المكالمة غير موجودة."
    if not _can_view_call(call, user):
        return None, "غير مصرح بعرض هذه المكالمة."
    return call, None


def accept_call_session(call: CallSession, teacher_user) -> tuple[CallSession | None, str | None]:
    if resolve_user_type_slug(teacher_user) != "teacher":
        return None, "هذا الإجراء للمعلّمين فقط."
    if call.teacher_id != teacher_user.id:
        return None, "غير مصرح بقبول هذه المكالمة."
    if call.status != CallSession.Status.PENDING:
        return None, "المكالمة ليست بانتظار القبول."

    now = timezone.now()
    call.status = CallSession.Status.ACTIVE
    call.started_at = call.started_at or now
    if not call.channel_name:
        assign_channel_name(call)
    ensure_agora_provider(call)
    call.save(update_fields=["status", "started_at", "updated_at"])

    from apps.calls.cloud_recording import start_cloud_recording_for_call

    try:
        start_cloud_recording_for_call(call)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Cloud recording start failed for call %s (call not affected)", call.id
        )

    return call, None


def reject_call_session(call: CallSession, teacher_user) -> tuple[CallSession | None, str | None]:
    if call.teacher_id != teacher_user.id:
        return None, "غير مصرح برفض هذه المكالمة."
    if call.status != CallSession.Status.PENDING:
        return None, "لا يمكن رفض هذه المكالمة."

    call.status = CallSession.Status.REJECTED
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at", "updated_at"])
    if call.teacher_id:
        mark_teacher_online(call.teacher)
    return call, None


def cancel_pending_call(call: CallSession, student_user) -> tuple[CallSession | None, str | None]:
    if call.student_id != student_user.id:
        return None, "غير مصرح بإلغاء هذه المكالمة."
    if call.status != CallSession.Status.PENDING:
        return None, "لا يمكن إلغاء هذه المكالمة."

    call.status = CallSession.Status.MISSED
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at", "updated_at"])
    if call.teacher_id:
        mark_teacher_online(call.teacher)
    return call, None


def end_call_session(call: CallSession, user) -> tuple[CallSession | None, str | None]:
    if not _can_view_call(call, user):
        return None, "غير مصرح بإنهاء هذه المكالمة."
    if call.status in {
        CallSession.Status.ENDED,
        CallSession.Status.REJECTED,
        CallSession.Status.MISSED,
        CallSession.Status.CANCELLED,
    }:
        return call, None

    call.status = CallSession.Status.ENDED
    call.ended_at = timezone.now()
    call.save(update_fields=["status", "ended_at", "updated_at"])
    if call.teacher_id:
        mark_teacher_online(call.teacher)

    from apps.calls.cloud_recording import stop_cloud_recording_for_call

    try:
        stop_cloud_recording_for_call(call)
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Cloud recording stop failed for call %s (call not affected)", call.id
        )

    from apps.calls.post_call import ensure_post_call_artifacts

    ensure_post_call_artifacts(call)
    return call, None


# Legacy immediate-start API (delegates to pending request for compatibility).
def create_call_session(
    user,
    *,
    session_type: str,
    teacher_id: int,
) -> CallSession:
    return request_call_session(
        user,
        session_type=session_type,
        teacher_id=teacher_id,
    )
