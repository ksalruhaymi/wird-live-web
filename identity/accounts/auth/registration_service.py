import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from apps.maqraa.models import StudentProfile, TeacherAvailability, TeacherProfile
from identity.accounts.auth.email_verification_service import consume_verification_token
from identity.accounts.user_types import (
    BLOCKED_REGISTRATION_SLUGS,
    MOBILE_REGISTRATION_SLUGS,
    USER_TYPE_STUDENT,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role

User = get_user_model()

_USERNAME_PATTERN = re.compile(r"^[\w.@+-]+$")
_IJAZAH_ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf"}
_IJAZAH_MAX_BYTES = 5 * 1024 * 1024


def parse_user_type(raw) -> tuple[int | None, str | None]:
    value = (raw or "").strip().lower()
    if value in BLOCKED_REGISTRATION_SLUGS:
        return None, "نوع الحساب غير صالح."
    if value in {"student", "طالب"}:
        return USER_TYPE_STUDENT, None
    if value in {"teacher", "معلم"}:
        return USER_TYPE_TEACHER, None
    if value in MOBILE_REGISTRATION_SLUGS:
        return None, "نوع الحساب غير صالح."
    return None, "نوع الحساب غير صالح. استخدم student أو teacher."


def parse_gender(raw) -> tuple[str | None, str | None]:
    value = (raw or "").strip().lower()
    if value in {"male", "ذكر", "m"}:
        return "male", None
    if value in {"female", "أنثى", "انثى", "f"}:
        return "female", None
    if not value:
        return None, "الجنس مطلوب."
    return None, "الجنس غير صالح."


def validate_ijazah_file(uploaded_file: UploadedFile | None) -> str | None:
    if uploaded_file is None:
        return "إجازة القرآن الكريم مطلوبة."
    name = (uploaded_file.name or "").lower()
    if not any(name.endswith(ext) for ext in _IJAZAH_ALLOWED_EXTENSIONS):
        return "نوع الملف غير مدعوم. استخدم png أو jpg أو jpeg أو pdf."
    if uploaded_file.size > _IJAZAH_MAX_BYTES:
        return "حجم الملف كبير جدًا. الحد الأقصى 5MB."
    return None


def username_from_email(email: str) -> str:
    """Local part before @, lowercased (e.g. admin@gmail.com -> admin)."""
    normalized = (email or "").strip().lower()
    if "@" not in normalized:
        return ""
    local, _domain = normalized.split("@", 1)
    local = local.strip()
    if not local or not _USERNAME_PATTERN.match(local):
        return ""
    return local


def _assign_role_for_user_type(user: User, user_type_value: int) -> None:
    slug = "teacher" if user_type_value == USER_TYPE_TEACHER else "student"
    role = Role.objects.filter(slug=slug).first()
    if role:
        user.roles.add(role)


@transaction.atomic
def register_account(
    *,
    full_name: str,
    email: str,
    password: str,
    user_type_value: int,
    gender: str | None = None,
    riwayat: str = "",
    ijazah_file: UploadedFile | None = None,
) -> User:
    username = username_from_email(email)

    user = User.objects.create_user(
        username=username,
        email=email.strip().lower(),
        password=password,
        full_name=full_name.strip(),
        user_type=user_type_value,
        gender=gender,
        created_by=None,
        is_staff=False,
        is_superuser=False,
    )

    _assign_role_for_user_type(user, user_type_value)

    if user_type_value == USER_TYPE_TEACHER:
        TeacherProfile.objects.create(
            user=user,
            display_name=full_name.strip(),
            riwayat=riwayat.strip(),
            ijazah=ijazah_file,
            is_approved=True,
            can_audio=True,
            can_video=True,
        )
        TeacherAvailability.objects.create(
            teacher=user,
            status=TeacherAvailability.Status.OFFLINE,
        )
    else:
        StudentProfile.objects.create(
            user=user,
            display_name=full_name.strip(),
        )

    return user


def validate_registration_payload(
    data: dict,
    *,
    ijazah_file: UploadedFile | None = None,
    require_verification_token: bool = False,
) -> tuple[dict | None, str | None]:
    full_name = (data.get("full_name") or data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    confirm_password = data.get("confirm_password") or data.get("password_confirm") or ""
    user_type_raw = data.get("user_type")
    verification_token = (data.get("verification_token") or "").strip()

    if not full_name:
        return None, "الاسم مطلوب."
    if not email:
        return None, "البريد الإلكتروني مطلوب."
    if "@" not in email:
        return None, "البريد الإلكتروني غير صالح."
    if not password:
        return None, "كلمة المرور مطلوبة."
    if confirm_password and confirm_password != password:
        return None, "كلمة المرور وتأكيدها غير متطابقين."

    if require_verification_token:
        if not verification_token:
            return None, "رمز التحقق من البريد مطلوب."
        if not consume_verification_token(email, verification_token):
            return None, "انتهت صلاحية التحقق من البريد. أعد المحاولة."

    user_type_value, type_err = parse_user_type(user_type_raw)
    if type_err:
        return None, type_err

    gender, gender_err = parse_gender(data.get("gender"))
    if gender_err:
        return None, gender_err

    if user_type_value not in (USER_TYPE_STUDENT, USER_TYPE_TEACHER):
        return None, "نوع الحساب غير صالح."

    riwayat = (data.get("riwayat") or "").strip()
    if user_type_value == USER_TYPE_TEACHER:
        if not riwayat:
            return None, "الروايات مطلوبة."
        ijazah_err = validate_ijazah_file(ijazah_file)
        if ijazah_err:
            return None, ijazah_err

    username = username_from_email(email)
    if not username:
        return None, "البريد الإلكتروني غير صالح."

    if User.objects.filter(username__iexact=username).exists():
        return None, (
            "اسم المستخدم المستخرج من هذا البريد مستخدم بالفعل. "
            "يرجى استخدام بريد إلكتروني آخر."
        )
    if User.objects.filter(email__iexact=email).exists():
        return None, "هذا البريد مستخدم مسبقًا"

    try:
        validate_password(password)
    except ValidationError as exc:
        return None, " ".join(exc.messages)

    return {
        "full_name": full_name,
        "email": email,
        "password": password,
        "user_type_value": user_type_value,
        "gender": gender,
        "riwayat": riwayat,
        "ijazah_file": ijazah_file,
    }, None
