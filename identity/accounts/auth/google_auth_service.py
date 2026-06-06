import logging
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth import login as auth_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.maqraa.models import StudentProfile, TeacherAvailability, TeacherProfile
from identity.accounts.auth.registration_service import (
    _assign_role_for_user_type,
    parse_gender,
    username_from_email,
    validate_ijazah_file,
)
from identity.accounts.auth.settings_service import is_db_login_allowed
from identity.accounts.user_types import (
    BLOCKED_REGISTRATION_SLUGS,
    USER_TYPE_STUDENT,
    USER_TYPE_TEACHER,
)

logger = logging.getLogger(__name__)

User = get_user_model()


@dataclass(frozen=True)
class GoogleAuthOutcome:
    status: str
    user: User | None = None
    message: str | None = None
    code: str | None = None
    http_status: int = 200


def _get_firebase_app():
    """Reuse the shared Firebase app initializer (FCM + auth)."""
    from apps.push.services import _get_firebase_app as get_app

    return get_app()


def verify_firebase_id_token(id_token: str) -> tuple[dict | None, str | None]:
    """
    Verify a Firebase ID token.

    Returns (decoded_claims, error_key).
    error_key is one of: config_error, invalid_token.
    """
    if not (id_token or "").strip():
        return None, "invalid_token"

    try:
        from firebase_admin import auth

        decoded = auth.verify_id_token(id_token.strip(), app=_get_firebase_app())
        return decoded, None
    except RuntimeError as exc:
        logger.error("Firebase is not configured: %s", exc)
        return None, "config_error"
    except Exception as exc:
        logger.warning("Firebase ID token verification failed: %s", exc)
        return None, "invalid_token"


def parse_google_user_type(raw) -> tuple[int | None, str | None, str | None]:
    """
    Map mobile user_type values to internal user_type + gender.

    Returns (user_type_value, gender, error_message).
    gender may be None when not specified.
    """
    value = (raw or "").strip().lower()
    if not value:
        return None, None, None

    if value in BLOCKED_REGISTRATION_SLUGS:
        return None, None, "نوع الحساب غير صالح."

    mapping = {
        "student": (USER_TYPE_STUDENT, "male"),
        "teacher": (USER_TYPE_TEACHER, "male"),
        "female_student": (USER_TYPE_STUDENT, "female"),
        "female_teacher": (USER_TYPE_TEACHER, "female"),
        "طالب": (USER_TYPE_STUDENT, "male"),
        "طالبة": (USER_TYPE_STUDENT, "female"),
        "معلم": (USER_TYPE_TEACHER, "male"),
        "معلمة": (USER_TYPE_TEACHER, "female"),
    }

    if value not in mapping:
        return None, None, "نوع الحساب غير صالح. استخدم student أو teacher."

    user_type_value, gender = mapping[value]
    return user_type_value, gender, None


def _login_session(request, user: User) -> GoogleAuthOutcome | None:
    if not user.is_active:
        return GoogleAuthOutcome(
            status="error",
            message="Account is inactive.",
            http_status=403,
        )
    if not user.is_superuser and not is_db_login_allowed():
        return GoogleAuthOutcome(
            status="error",
            message="Login is disabled.",
            http_status=403,
        )

    auth_login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return None


@transaction.atomic
def _register_google_user(
    *,
    email: str,
    full_name: str,
    firebase_uid: str,
    user_type_value: int,
    gender: str | None,
    riwayat: str = "",
    ijazah_file=None,
    password: str | None = None,
) -> User:
    username = username_from_email(email)
    if not username:
        raise ValueError("invalid_email")

    if User.objects.filter(username__iexact=username).exists():
        raise ValueError("username_taken")
    if User.objects.filter(email__iexact=email).exists():
        raise ValueError("email_taken")
    if User.objects.filter(firebase_uid=firebase_uid).exists():
        raise ValueError("firebase_uid_taken")

    user = User(
        username=username,
        email=email.strip().lower(),
        full_name=full_name.strip(),
        user_type=user_type_value,
        firebase_uid=firebase_uid,
        gender=gender or None,
        created_by=None,
        is_staff=False,
        is_superuser=False,
    )
    if password:
        user.set_password(password)
    else:
        user.set_unusable_password()
    user.save()

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


def authenticate_with_google(request, data: dict, *, ijazah_file=None) -> GoogleAuthOutcome:
    id_token = (data.get("id_token") or "").strip()
    client_uid = (data.get("firebase_uid") or "").strip()

    decoded, verify_error = verify_firebase_id_token(id_token)
    if verify_error == "config_error":
        return GoogleAuthOutcome(
            status="error",
            message="Firebase is not configured on the server.",
            http_status=503,
        )
    if decoded is None:
        return GoogleAuthOutcome(
            status="error",
            message="Invalid Firebase ID token.",
            http_status=401,
        )

    verified_uid = (decoded.get("uid") or decoded.get("sub") or "").strip()
    if not verified_uid:
        return GoogleAuthOutcome(
            status="error",
            message="Invalid Firebase ID token.",
            http_status=401,
        )

    if client_uid and client_uid != verified_uid:
        return GoogleAuthOutcome(
            status="error",
            message="Firebase UID mismatch.",
            http_status=401,
        )

    verified_email = (decoded.get("email") or "").strip().lower()
    verified_name = (
        (decoded.get("name") or "").strip()
        or (data.get("display_name") or "").strip()
    )

    user = User.objects.filter(firebase_uid=verified_uid).first()
    if user is not None:
        login_error = _login_session(request, user)
        if login_error:
            return login_error
        return GoogleAuthOutcome(status="ok", user=user, http_status=200)

    if verified_email:
        email_user = User.objects.filter(email__iexact=verified_email).first()
        if email_user is not None:
            existing_uid = (email_user.firebase_uid or "").strip()
            if existing_uid and existing_uid != verified_uid:
                return GoogleAuthOutcome(
                    status="error",
                    message="Email is linked to another Firebase account.",
                    http_status=401,
                )

            email_user.firebase_uid = verified_uid
            if verified_name and not (email_user.full_name or "").strip():
                email_user.full_name = verified_name
            email_user.save(update_fields=["firebase_uid", "full_name"])

            login_error = _login_session(request, email_user)
            if login_error:
                return login_error
            return GoogleAuthOutcome(status="ok", user=email_user, http_status=200)

    user_type_raw = data.get("user_type")
    user_type_value, gender_from_type, type_error = parse_google_user_type(user_type_raw)
    gender_override, gender_error = parse_gender(data.get("gender"))
    if gender_error and user_type_value is not None:
        return GoogleAuthOutcome(status="error", message=gender_error, http_status=400)
    gender = gender_override or gender_from_type
    if type_error:
        return GoogleAuthOutcome(
            status="error",
            message=type_error,
            http_status=400,
        )
    if user_type_value is None:
        return GoogleAuthOutcome(
            status="account_type_required",
            message="نوع الحساب مطلوب",
            code="account_type_required",
            http_status=400,
        )

    riwayat = (data.get("riwayat") or "").strip()
    if user_type_value == USER_TYPE_TEACHER:
        if not riwayat:
            return GoogleAuthOutcome(
                status="error",
                message="الروايات مطلوبة.",
                http_status=400,
            )
        ijazah_err = validate_ijazah_file(ijazah_file)
        if ijazah_err:
            return GoogleAuthOutcome(status="error", message=ijazah_err, http_status=400)

    if not is_db_login_allowed():
        return GoogleAuthOutcome(
            status="error",
            message="Registration is disabled.",
            http_status=403,
        )

    if not verified_email:
        return GoogleAuthOutcome(
            status="error",
            message="Email is required to create an account.",
            http_status=400,
        )

    display_name = verified_name or (data.get("full_name") or "").strip() or verified_email.split("@", 1)[0]
    password = (data.get("password") or "").strip()
    confirm_password = (data.get("confirm_password") or data.get("password_confirm") or "").strip()
    if password:
        if confirm_password and confirm_password != password:
            return GoogleAuthOutcome(
                status="error",
                message="كلمة المرور وتأكيدها غير متطابقين.",
                http_status=400,
            )
        try:
            validate_password(password)
        except ValidationError as exc:
            return GoogleAuthOutcome(
                status="error",
                message=" ".join(exc.messages),
                http_status=400,
            )

    try:
        user = _register_google_user(
            email=verified_email,
            full_name=display_name,
            firebase_uid=verified_uid,
            user_type_value=user_type_value,
            gender=gender,
            riwayat=riwayat,
            ijazah_file=ijazah_file,
            password=password or None,
        )
    except ValueError as exc:
        code = str(exc)
        if code == "username_taken":
            return GoogleAuthOutcome(
                status="error",
                message=(
                    "اسم المستخدم المستخرج من هذا البريد مستخدم بالفعل. "
                    "يرجى استخدام بريد إلكتروني آخر."
                ),
                http_status=400,
            )
        if code == "email_taken":
            return GoogleAuthOutcome(
                status="error",
                message="البريد الإلكتروني مستخدم بالفعل.",
                http_status=400,
            )
        if code == "invalid_email":
            return GoogleAuthOutcome(
                status="error",
                message="البريد الإلكتروني غير صالح.",
                http_status=400,
            )
        return GoogleAuthOutcome(
            status="error",
            message="Unable to create account.",
            http_status=400,
        )

    login_error = _login_session(request, user)
    if login_error:
        return login_error

    return GoogleAuthOutcome(status="ok", user=user, http_status=201)
