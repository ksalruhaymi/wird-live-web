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


def teacher_display_name(user) -> str:
    profile = getattr(user, "teacher_profile", None)
    if profile and profile.display_name:
        return profile.display_name
    full = (getattr(user, "full_name", "") or "").strip()
    return full or user.username


def _active_teacher_ids() -> set[int]:
    from apps.calls.models import CallSession

    return set(
        CallSession.objects.filter(
            status=CallSession.Status.ACTIVE,
            teacher_id__isnull=False,
        ).values_list("teacher_id", flat=True)
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

    return {
        "id": user.id,
        "full_name": teacher_display_name(user),
        "username": user.username,
        "status": status,
        "can_audio": profile.can_audio if profile else False,
        "can_video": profile.can_video if profile else False,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "profile_image_url": _resolve_profile_image_url(user, request),
        "riwayat": (getattr(profile, "riwayat", "") or "").strip() or None,
        "rating_percent": rating_percent if rating_percent is not None else 0,
    }


def list_teachers_payload(*, approved_only: bool = True, request=None) -> list[dict]:
    qs = User.objects.filter(teacher_profile__isnull=False).select_related(
        "teacher_profile",
        "teacher_availability",
    )
    if approved_only:
        qs = qs.filter(teacher_profile__is_approved=True)
    qs = qs.order_by("teacher_profile__display_name", "username")
    active_ids = _active_teacher_ids()
    users = list(qs)
    from apps.calls.rating_service import teacher_rating_percents

    rating_map = teacher_rating_percents([user.id for user in users])
    return [
        teacher_to_payload(
            user,
            active_teacher_ids=active_ids,
            request=request,
            rating_percent=rating_map.get(user.id, 0),
        )
        for user in users
    ]


def get_teacher_user(teacher_id: int):
    try:
        user = User.objects.select_related(
            "teacher_profile",
            "teacher_availability",
        ).get(pk=teacher_id, teacher_profile__isnull=False)
    except User.DoesNotExist:
        return None
    if not user.teacher_profile.is_approved:
        return None
    return user


def validate_teacher_for_call(teacher, *, session_type: str) -> str | None:
    profile = teacher.teacher_profile
    status = compute_teacher_status(teacher)

    if status == COMPUTED_OFFLINE:
        return "المعلّم غير متصل حاليًا."
    if status == COMPUTED_BUSY:
        return "المعلّم مشغول الآن."

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
