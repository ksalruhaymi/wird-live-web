"""Build and update mobile user profile payloads."""

import mimetypes

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import UploadedFile
from django.urls import reverse

from apps.maqraa.models import StudentProfile, TeacherProfile
from core.services.phone_service import normalize_phone_number
from identity.accounts.user_types import USER_TYPE_STUDENT, USER_TYPE_TEACHER, resolve_user_type_slug

User = get_user_model()

_GENDER_LABELS = {
    "male": "ذكر",
    "female": "أنثى",
}

_AVATAR_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
_AVATAR_MAX_BYTES = 2 * 1024 * 1024

_IJAZAH_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _display_name(user) -> str:
    name = (getattr(user, "full_name", None) or "").strip()
    if name:
        return name
    full = (user.get_full_name() or "").strip()
    return full or user.username


def _resolve_profile_image_url(user, request) -> str | None:
    if not hasattr(user, "profile_image"):
        return None
    image = getattr(user, "profile_image", None)
    if not image:
        return None
    try:
        relative = image.url
    except (ValueError, AttributeError):
        return None
    if request is not None:
        return request.build_absolute_uri(relative)
    return relative


def _resolve_riwayat(user) -> str:
    try:
        teacher_profile = user.teacher_profile
        return (getattr(teacher_profile, "riwayat", "") or "").strip()
    except Exception:
        pass
    try:
        student_profile = user.student_profile
        return (getattr(student_profile, "riwayat", "") or "").strip()
    except Exception:
        pass
    return ""


def ijazah_file_kind(filename: str) -> str:
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if f".{ext}" in _IJAZAH_IMAGE_EXTENSIONS:
        return "image"
    if ext == "pdf":
        return "pdf"
    return "file"


def ijazah_is_image(filename: str) -> bool:
    return ijazah_file_kind(filename) == "image"


def get_teacher_ijazah_file(user):
    """Return the logged-in teacher's ijazah field, or None."""
    if resolve_user_type_slug(user) != USER_TYPE_TEACHER:
        return None
    profile = getattr(user, "teacher_profile", None)
    if profile is None:
        return None
    ijazah = getattr(profile, "ijazah", None)
    if not ijazah or not ijazah.name:
        return None
    return ijazah


def build_teacher_files_payload(user, request=None) -> list[dict]:
    if resolve_user_type_slug(user) != USER_TYPE_TEACHER:
        return []

    ijazah = get_teacher_ijazah_file(user)
    if ijazah is None:
        return []

    filename = ijazah.name.rsplit("/", 1)[-1]
    url_path = reverse("accounts_auth_api:profile_teacher_ijazah")
    url = request.build_absolute_uri(url_path) if request is not None else url_path
    return [
        {
            "type": "ijazah",
            "label": "ملف الإجازة",
            "url": url,
            "file_name": filename,
            "is_image": ijazah_is_image(filename),
        }
    ]


def build_profile_payload(user, request=None) -> dict:
    gender = (user.gender or "").strip() or None
    return {
        "id": user.id,
        "username": user.username,
        "full_name": (user.full_name or "").strip(),
        "display_name": _display_name(user),
        "gender": gender,
        "gender_label": _GENDER_LABELS.get(gender or ""),
        "mobile": (user.mobile or "").strip(),
        "email": (user.email or "").strip(),
        "riwayat": _resolve_riwayat(user),
        "profile_image_url": _resolve_profile_image_url(user, request),
        "user_type": resolve_user_type_slug(user),
        "teacher_files": build_teacher_files_payload(user, request),
    }


def validate_avatar_file(uploaded_file: UploadedFile | None) -> str | None:
    if uploaded_file is None:
        return "صورة الملف الشخصي مطلوبة."
    name = (uploaded_file.name or "").lower()
    if not any(name.endswith(ext) for ext in _AVATAR_ALLOWED_EXTENSIONS):
        return "نوع الصورة غير مدعوم. استخدم png أو jpg أو jpeg."
    if uploaded_file.size > _AVATAR_MAX_BYTES:
        return "حجم الصورة كبير جدًا. الحد الأقصى 2MB."
    return None


def update_profile_fields(
    user,
    data: dict,
    *,
    request=None,
) -> tuple[dict | None, str | None]:
    update_fields: list[str] = []

    if "mobile" in data:
        mobile_raw = (data.get("mobile") or "").strip()
        mobile_db = None
        if mobile_raw:
            try:
                mobile_db = normalize_phone_number(mobile_raw, "SA")
            except ValueError as exc:
                return None, str(exc)
            if User.objects.filter(mobile=mobile_db).exclude(id=user.id).exists():
                return None, "رقم الجوال مستخدم مسبقًا."
        user.mobile = mobile_db
        update_fields.append("mobile")

    if "riwayat" in data:
        riwayat = (data.get("riwayat") or "").strip()
        user_type = getattr(user, "user_type", None)
        if user_type == USER_TYPE_TEACHER:
            profile, _ = TeacherProfile.objects.get_or_create(user=user)
            profile.riwayat = riwayat
            profile.save(update_fields=["riwayat", "updated_at"])
        elif user_type == USER_TYPE_STUDENT:
            profile, _ = StudentProfile.objects.get_or_create(user=user)
            profile.riwayat = riwayat
            profile.save(update_fields=["riwayat", "updated_at"])

    if update_fields:
        user.save(update_fields=update_fields)

    return build_profile_payload(user, request), None


def update_profile_avatar(
    user,
    uploaded_file: UploadedFile,
    request=None,
) -> tuple[dict | None, str | None]:
    error = validate_avatar_file(uploaded_file)
    if error:
        return None, error
    if not hasattr(user, "profile_image"):
        return None, "تحديث الصورة غير متاح على الخادم بعد."
    user.profile_image = uploaded_file
    user.save(update_fields=["profile_image"])
    return build_profile_payload(user, request), None
