import hashlib
import logging
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from identity.accounts.models import EmailRegistrationVerification

logger = logging.getLogger(__name__)

User = get_user_model()

_CODE_TTL_MINUTES = 10
_TOKEN_TTL_MINUTES = 30

# Distinct from OTP expiry — used only for post-verify registration completion.
REGISTRATION_SESSION_EXPIRED_MESSAGE = (
    "انتهت صلاحية جلسة إكمال التسجيل. أعد التحقق من البريد."
)
REGISTRATION_SESSION_INVALID_MESSAGE = (
    "جلسة إكمال التسجيل غير صالحة. أعد التحقق من البريد."
)
REGISTRATION_SESSION_REQUIRED_MESSAGE = "جلسة إكمال التسجيل مطلوبة."
REGISTRATION_SESSION_EXPIRED_CODE = "registration_session_expired"
REGISTRATION_SESSION_INVALID_CODE = "registration_session_invalid"


class RegistrationSessionError(Exception):
    def __init__(self, message: str, *, code: str):
        self.message = message
        self.code = code
        super().__init__(message)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(10000):04d}"


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def check_email_available(email: str) -> tuple[bool, str | None]:
    normalized = (email or "").strip().lower()
    if not normalized or "@" not in normalized:
        return False, "البريد الإلكتروني غير صالح."
    if User.objects.filter(email__iexact=normalized).exists():
        return False, "هذا البريد مستخدم مسبقًا"
    return True, None


def send_registration_code(email: str) -> tuple[bool, str | None]:
    available, message = check_email_available(email)
    if not available:
        return False, message

    normalized = email.strip().lower()
    code = _generate_code()
    now = timezone.now()

    EmailRegistrationVerification.objects.filter(
        email__iexact=normalized,
        verified_at__isnull=True,
    ).delete()

    EmailRegistrationVerification.objects.create(
        email=normalized,
        code_hash=_hash_code(code),
        expires_at=now + timedelta(minutes=_CODE_TTL_MINUTES),
    )

    try:
        send_mail(
            subject="رمز التحقق - وِرد لايف",
            message=f"رمز التحقق الخاص بك هو: {code}",
            from_email=None,
            recipient_list=[normalized],
            fail_silently=False,
        )
    except Exception as exc:
        logger.exception("Failed to send verification email: %s", exc)
        return False, "تعذر إرسال رمز التحقق. حاول مرة أخرى لاحقًا."

    return True, None


def verify_registration_code(email: str, code: str) -> tuple[str | None, str | None]:
    """Verify OTP once and issue a registration-session token (not the OTP)."""
    normalized = (email or "").strip().lower()
    raw_code = (code or "").strip()
    if not normalized or len(raw_code) != 4 or not raw_code.isdigit():
        return None, "رمز التحقق غير صالح."

    record = (
        EmailRegistrationVerification.objects.filter(
            email__iexact=normalized,
            verified_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if record is None:
        return None, "رمز التحقق غير صالح."

    if record.expires_at < timezone.now():
        return None, "انتهت صلاحية رمز التحقق."

    if record.code_hash != _hash_code(raw_code):
        return None, "رمز التحقق غير صالح."

    token = _generate_token()
    now = timezone.now()
    record.verified_at = now
    record.verification_token = token
    record.token_expires_at = now + timedelta(minutes=_TOKEN_TTL_MINUTES)
    # Invalidate OTP reuse without prolonging OTP TTL.
    record.code_hash = _hash_code(secrets.token_hex(8))
    record.expires_at = now
    record.save(
        update_fields=[
            "verified_at",
            "verification_token",
            "token_expires_at",
            "code_hash",
            "expires_at",
        ],
    )
    return token, None


def _load_registration_session(email: str, token: str, *, for_update: bool = False):
    normalized = (email or "").strip().lower()
    raw_token = (token or "").strip()
    if not normalized or not raw_token:
        return None, RegistrationSessionError(
            REGISTRATION_SESSION_REQUIRED_MESSAGE,
            code=REGISTRATION_SESSION_INVALID_CODE,
        )

    qs = EmailRegistrationVerification.objects.filter(
        email__iexact=normalized,
        verification_token=raw_token,
        verified_at__isnull=False,
    )
    if for_update:
        qs = qs.select_for_update()
    record = qs.first()
    if record is None:
        return None, RegistrationSessionError(
            REGISTRATION_SESSION_INVALID_MESSAGE,
            code=REGISTRATION_SESSION_INVALID_CODE,
        )
    if record.token_expires_at and record.token_expires_at < timezone.now():
        return None, RegistrationSessionError(
            REGISTRATION_SESSION_EXPIRED_MESSAGE,
            code=REGISTRATION_SESSION_EXPIRED_CODE,
        )
    return record, None


def validate_registration_session(email: str, token: str) -> None:
    """Ensure the post-OTP registration session is valid. Does not consume it."""
    _record, err = _load_registration_session(email, token, for_update=False)
    if err:
        raise err


def consume_registration_session(email: str, token: str) -> None:
    """
    One-time consume of the registration session (delete proof).

    Must be called inside an atomic block with user creation so a failed
    registration rolls the consume back.
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("consume_registration_session requires an atomic block")

    record, err = _load_registration_session(email, token, for_update=True)
    if err:
        raise err
    assert record is not None
    record.delete()


# Backward-compatible alias used by older call sites/tests.
def consume_verification_token(email: str, token: str) -> bool:
    try:
        with transaction.atomic():
            consume_registration_session(email, token)
        return True
    except RegistrationSessionError:
        return False
