from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse

from identity.accounts.auth.profile_service import (
    _resolve_profile_image_url,
    build_profile_payload,
    ijazah_file_kind,
)
from identity.accounts.user_types import USER_TYPE_TEACHER, user_type_label

from .models import TeacherProfile
from .teacher_approval_service import teacher_approval_payload
from .teacher_services import teacher_display_name

User = get_user_model()

_GENDER_LABELS = {
    "male": "ذكر",
    "female": "أنثى",
}


def gender_label(user) -> str:
    gender = (getattr(user, "gender", None) or "").strip()
    return _GENDER_LABELS.get(gender, "—")


def build_management_teacher_files(user, request=None) -> list[dict]:
    files = []
    profile_image = getattr(user, "profile_image", None)
    if profile_image and profile_image.name:
        filename = profile_image.name.rsplit("/", 1)[-1]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        url_path = reverse(
            "tutoring_api:management-teacher-profile-image",
            kwargs={"teacher_id": user.id},
        )
        url = request.build_absolute_uri(url_path) if request else url_path
        files.append(
            {
                "type": "profile_image",
                "label": "الصورة الشخصية",
                "file_name": filename,
                "kind": "image" if ext in {"png", "jpg", "jpeg", "gif", "webp"} else "file",
                "url": url,
                "is_image": ext in {"png", "jpg", "jpeg", "gif", "webp"},
            }
        )

    profile = getattr(user, "teacher_profile", None)
    ijazah = getattr(profile, "ijazah", None) if profile else None
    if ijazah and ijazah.name:
        filename = ijazah.name.rsplit("/", 1)[-1]
        url_path = reverse(
            "tutoring_api:management-teacher-ijazah",
            kwargs={"teacher_id": user.id},
        )
        url = request.build_absolute_uri(url_path) if request else url_path
        files.append(
            {
                "type": "ijazah",
                "label": "ملف الإجازة",
                "file_name": filename,
                "kind": ijazah_file_kind(filename),
                "url": url,
                "is_image": ijazah_file_kind(filename) == "image",
            }
        )
    return files


def pending_teacher_card_payload(user, request=None) -> dict:
    profile = user.teacher_profile
    return {
        "id": user.id,
        "full_name": teacher_display_name(user),
        "username": user.username,
        "email": user.email or "",
        "mobile": user.mobile or "",
        "riwayat": (profile.riwayat or "").strip(),
        "profile_image_url": _resolve_profile_image_url(user, request),
        "can_audio": bool(profile.can_audio),
        "can_video": bool(profile.can_video),
        "submitted_at": profile.created_at.isoformat() if profile.created_at else None,
    }


def teacher_review_detail_payload(user, request=None) -> dict:
    profile = user.teacher_profile
    profile_data = build_profile_payload(user, request)
    return {
        "id": user.id,
        "username": user.username,
        "full_name": (user.full_name or "").strip(),
        "display_name": profile_data.get("display_name") or user.username,
        "email": user.email or "",
        "mobile": user.mobile or "",
        "gender": profile_data.get("gender"),
        "gender_label": gender_label(user),
        "user_type_label": user_type_label(user),
        "national_id": user.national_id or "",
        "qualification": user.qualification or "",
        "birth_date": user.birth_date.isoformat() if user.birth_date else None,
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        "is_active": user.is_active,
        "riwayat": profile_data.get("riwayat") or "",
        "bio": (profile.bio or "").strip(),
        "profile_image_url": profile_data.get("profile_image_url"),
        "teacher_files": build_management_teacher_files(user, request),
        "approval": teacher_approval_payload(profile),
        "is_pending": profile.approval_status
        == TeacherProfile.ApprovalStatus.PENDING,
    }


def list_pending_teachers(*, q: str = ""):
    qs = User.objects.filter(
        user_type=USER_TYPE_TEACHER,
        teacher_profile__isnull=False,
        teacher_profile__approval_status=TeacherProfile.ApprovalStatus.PENDING,
    ).select_related("teacher_profile")

    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(full_name__icontains=q)
            | Q(mobile__icontains=q)
            | Q(teacher_profile__display_name__icontains=q)
        )

    return list(qs.order_by("-teacher_profile__created_at", "username"))
