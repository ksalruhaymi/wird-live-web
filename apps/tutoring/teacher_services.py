from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from identity.accounts.auth.profile_service import _resolve_profile_image_url
from identity.accounts.user_types import (
    USER_TYPE_STUDENT,
    USER_TYPE_TEACHER,
    resolve_user_type_slug,
)

from .models import TeacherAvailability, TeacherProfile
from .teacher_approval_service import is_teacher_list_visible

User = get_user_model()

# Computed presence (API + dashboard); not stored on TeacherAvailability.status.
COMPUTED_AVAILABLE = "available"
COMPUTED_BUSY = "busy"
COMPUTED_OFFLINE = "offline"

TEACHER_PRESENCE_TTL_MINUTES = 5

COMPUTED_STATUS_LABELS_AR = {
    COMPUTED_AVAILABLE: "متاح",
    COMPUTED_BUSY: "مشغول",
    COMPUTED_OFFLINE: "غير متصل",
}

# Test-call UX constants (independent service; not tied to any teacher user).
DEMO_CALL_MESSAGE = (
    "مرحبًا، هذا اتصال تجريبي. تحدث الآن لاختبار جودة صوتك، "
    "وسينتهي الاتصال بعد دقيقة واحدة."
)
DEMO_CALL_TIME_LIMIT_MESSAGE = "انتهت مدة الاتصال التجريبي"
DEMO_CALL_MAX_SECONDS = 60


def auto_accepts_calls(user) -> bool:
    profile = getattr(user, "teacher_profile", None)
    return bool(profile and profile.auto_accept_calls)


def teacher_display_name(user) -> str:
    profile = getattr(user, "teacher_profile", None)
    if profile and profile.display_name:
        return profile.display_name
    full = (getattr(user, "full_name", "") or "").strip()
    return full or user.username


def _active_teacher_ids() -> set[int]:
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from apps.calls.models import CallSession

    # Only real in-progress calls block. Recording processing never blocks.
    # Ignore stale ENDING rows so a hung end cannot lock the teacher forever.
    ending_cutoff = timezone.now() - timedelta(minutes=2)
    return set(
        CallSession.objects.filter(
            teacher_id__isnull=False,
        )
        .filter(
            Q(status=CallSession.Status.ACTIVE)
            | Q(
                status=CallSession.Status.ENDING,
                end_requested_at__gt=ending_cutoff,
            )
            | Q(
                status=CallSession.Status.ENDING,
                end_requested_at__isnull=True,
                updated_at__gt=ending_cutoff,
            )
        )
        .values_list("teacher_id", flat=True)
    )


def compute_teacher_status(
    user,
    *,
    active_teacher_ids: set[int] | None = None,
    now=None,
) -> str:
    """Derive teacher presence from active calls and last_seen heartbeat."""
    if active_teacher_ids is None:
        active_teacher_ids = _active_teacher_ids()

    if user.id in active_teacher_ids:
        return COMPUTED_BUSY

    last_seen = (
        TeacherAvailability.objects.filter(teacher_id=user.id)
        .values_list("last_seen", flat=True)
        .first()
    )
    if not last_seen:
        return COMPUTED_OFFLINE

    now = now or timezone.now()
    if now - last_seen <= timedelta(minutes=TEACHER_PRESENCE_TTL_MINUTES):
        return COMPUTED_AVAILABLE

    return COMPUTED_OFFLINE


def computed_status_label(status: str) -> str:
    return COMPUTED_STATUS_LABELS_AR.get(status, status)


def touch_teacher_last_seen(teacher) -> None:
    availability, _ = TeacherAvailability.objects.get_or_create(
        teacher=teacher,
        defaults={"status": TeacherAvailability.Status.OFFLINE},
    )
    availability.last_seen = timezone.now()
    availability.save(update_fields=["last_seen", "updated_at"])


def record_teacher_heartbeat(user) -> TeacherAvailability:
    if resolve_user_type_slug(user) != "teacher":
        raise PermissionError("heartbeat is for teachers only")
    touch_teacher_last_seen(user)
    return user.teacher_availability


def teacher_to_payload(
    user,
    *,
    active_teacher_ids: set[int] | None = None,
    request=None,
    rating_percent: int | None = None,
) -> dict:
    profile = getattr(user, "teacher_profile", None)
    availability = getattr(user, "teacher_availability", None)
    last_seen = availability.last_seen if availability else None
    status = compute_teacher_status(
        user,
        active_teacher_ids=active_teacher_ids,
    )
    status_label = computed_status_label(status)

    return {
        "id": user.id,
        "full_name": teacher_display_name(user),
        "username": user.username,
        "status": status,
        "status_label": status_label,
        "can_audio": profile.can_audio if profile else False,
        "can_video": profile.can_video if profile else False,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "profile_image_url": _resolve_profile_image_url(user, request),
        "riwayat": (getattr(profile, "riwayat", "") or "").strip() or None,
        "rating_percent": rating_percent if rating_percent is not None else 0,
        "auto_accept_calls": bool(profile and profile.auto_accept_calls),
    }


def list_teachers_payload(*, approved_only: bool = True, request=None) -> list[dict]:
    qs = User.objects.filter(teacher_profile__isnull=False).select_related(
        "teacher_profile",
        "teacher_availability",
    )
    if approved_only:
        qs = qs.filter(
            teacher_profile__approval_status=TeacherProfile.ApprovalStatus.APPROVED
        )
    qs = qs.order_by("teacher_profile__display_name", "username")
    active_ids = _active_teacher_ids()
    users = list(qs)
    from apps.calls.rating_service import teacher_rating_percents

    rating_map = teacher_rating_percents([user.id for user in users])
    payloads = [
        teacher_to_payload(
            user,
            active_teacher_ids=active_ids,
            request=request,
            rating_percent=rating_map.get(user.id, 0),
        )
        for user in users
    ]
    try:
        from apps.appointments.services.teacher_list_summary import (
            booking_card_summaries_for_teachers,
        )

        summaries = booking_card_summaries_for_teachers([u.id for u in users])
        for payload in payloads:
            payload["booking"] = summaries.get(
                payload["id"],
                {
                    "booking_enabled": True,
                    "has_available_slots": False,
                    "nearest_slot": None,
                    "message_code": "no_slots",
                },
            )
    except Exception:
        # Appointments app optional for older deployments mid-migrate.
        for payload in payloads:
            payload.setdefault("booking", None)
    return payloads


def get_teacher_user(teacher_id: int):
    try:
        user = User.objects.select_related(
            "teacher_profile",
            "teacher_availability",
        ).get(pk=teacher_id, teacher_profile__isnull=False)
    except User.DoesNotExist:
        return None
    if not is_teacher_list_visible(user.teacher_profile):
        return None
    return user


def get_pending_teacher_for_interview(teacher_id: int):
    """Return a pending teacher for admin/supervisor interview calls only."""
    try:
        user = User.objects.select_related(
            "teacher_profile",
            "teacher_availability",
        ).get(pk=teacher_id, teacher_profile__isnull=False)
    except User.DoesNotExist:
        return None
    profile = user.teacher_profile
    if profile.approval_status != TeacherProfile.ApprovalStatus.PENDING:
        return None
    return user


def validate_teacher_for_call(
    teacher,
    *,
    session_type: str,
    interview_call: bool = False,
) -> str | None:
    profile = teacher.teacher_profile
    status = compute_teacher_status(teacher)

    if status == COMPUTED_BUSY:
        return "المعلّم مشغول الآن."
    if not interview_call and status == COMPUTED_OFFLINE:
        return "المعلّم غير متصل حاليًا."

    if session_type == "audio" and not profile.can_audio:
        return "هذا المعلّم لا يدعم الاتصال الصوتي."
    if session_type == "video" and not profile.can_video:
        return "هذا المعلّم لا يدعم الاتصال المرئي."
    return None


def mark_teacher_busy(teacher) -> None:
    # Presence busy is derived from active CallSession; only refresh last_seen.
    touch_teacher_last_seen(teacher)


def mark_teacher_online(teacher) -> None:
    touch_teacher_last_seen(teacher)


def search_teacher_rows(q: str):
    qs = User.objects.filter(teacher_profile__isnull=False).select_related(
        "teacher_profile",
        "teacher_availability",
    )
    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(full_name__icontains=q)
            | Q(teacher_profile__display_name__icontains=q)
        )
    return qs.order_by("teacher_profile__display_name", "username")
