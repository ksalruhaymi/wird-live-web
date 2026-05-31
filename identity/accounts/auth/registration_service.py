from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.maqraa.models import StudentProfile, TeacherAvailability, TeacherProfile
from identity.accounts.user_types import (
    BLOCKED_REGISTRATION_SLUGS,
    MOBILE_REGISTRATION_SLUGS,
    USER_TYPE_STUDENT,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role

User = get_user_model()


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


def username_from_email(email: str) -> str:
    return email.strip().lower()


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
) -> User:
    username = username_from_email(email)

    user = User.objects.create_user(
        username=username,
        email=email.strip().lower(),
        password=password,
        full_name=full_name.strip(),
        user_type=user_type_value,
        created_by=None,
        is_staff=False,
        is_superuser=False,
    )

    _assign_role_for_user_type(user, user_type_value)

    if user_type_value == USER_TYPE_TEACHER:
        TeacherProfile.objects.create(
            user=user,
            display_name=full_name.strip(),
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


def validate_registration_payload(data: dict) -> tuple[dict | None, str | None]:
    full_name = (data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user_type_raw = data.get("user_type")

    if not full_name:
        return None, "الاسم الرباعي مطلوب."
    if not email:
        return None, "البريد الإلكتروني مطلوب."
    if "@" not in email:
        return None, "البريد الإلكتروني غير صالح."
    if not password:
        return None, "كلمة المرور مطلوبة."

    user_type_value, type_err = parse_user_type(user_type_raw)
    if type_err:
        return None, type_err

    if user_type_value not in (USER_TYPE_STUDENT, USER_TYPE_TEACHER):
        return None, "نوع الحساب غير صالح."

    username = username_from_email(email)
    if User.objects.filter(username=username).exists():
        return None, "البريد الإلكتروني مستخدم بالفعل."
    if User.objects.filter(email__iexact=email).exists():
        return None, "البريد الإلكتروني مستخدم بالفعل."

    try:
        validate_password(password)
    except ValidationError as exc:
        return None, " ".join(exc.messages)

    return {
        "full_name": full_name,
        "email": email,
        "password": password,
        "user_type_value": user_type_value,
    }, None
