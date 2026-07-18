import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from identity.accounts.models import EmailRegistrationVerification

logger = logging.getLogger(__name__)

User = get_user_model()

_CODE_TTL_MINUTES = 10
_TOKEN_TTL_MINUTES = 30
_RESEND_COOLDOWN_SECONDS = 60

OTP_EXPIRED_MESSAGE = "انتهت صلاحية رمز التحقق."
OTP_INVALID_MESSAGE = "رمز التحقق غير صالح."
OTP_EXPIRED_CODE = "otp_expired"
OTP_RESEND_COOLDOWN_CODE = "otp_resend_cooldown"
OTP_RESEND_COOLDOWN_MESSAGE = "يرجى الانتظار قبل إعادة إرسال رمز التحقق."
EMAIL_ALREADY_REGISTERED_CODE = "email_already_registered"
EMAIL_ALREADY_REGISTERED_MESSAGE = (
    "البريد الإلكتروني مسجل مسبقًا. سجّل الدخول أو استخدم بريدًا آخر."
)

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


@dataclass(frozen=True)
class SendRegistrationCodeResult:
    ok: bool
    message: str | None = None
    error_code: str | None = None
    expires_at: datetime | None = None
    expires_in_seconds: int | None = None
    server_time: datetime | None = None
    resend_available_in_seconds: int | None = None


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(10000):04d}"


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def normalize_registration_email(email: str) -> str:
    """Strip + UserManager.normalize_email + lowercase for case-insensitive checks."""
    raw = (email or "").strip()
    if not raw:
        return ""
    try:
        normalized = User.objects.normalize_email(raw)
    except Exception:
        normalized = raw
    return (normalized or raw).strip().lower()


def check_email_available(email: str) -> tuple[bool, str | None, str | None]:
    """Returns (available, message, error_code)."""
    normalized = normalize_registration_email(email)
    if not normalized or "@" not in normalized:
        return False, "البريد الإلكتروني غير صالح.", None
    if User.objects.filter(email__iexact=normalized).exists():
        return False, EMAIL_ALREADY_REGISTERED_MESSAGE, EMAIL_ALREADY_REGISTERED_CODE
    return True, None, None


def _resend_wait_seconds(email: str, now: datetime) -> int:
    latest = (
        EmailRegistrationVerification.objects.filter(email__iexact=email)
        .order_by("-created_at")
        .first()
    )
    if latest is None:
        return 0
    elapsed = (now - latest.created_at).total_seconds()
    remaining = _RESEND_COOLDOWN_SECONDS - int(elapsed)
    return max(0, remaining)


def send_registration_code(email: str) -> SendRegistrationCodeResult:
    now = timezone.now()
    available, message, error_code = check_email_available(email)
    if not available:
        return SendRegistrationCodeResult(
            ok=False,
            message=message,
            error_code=error_code,
            server_time=now,
        )

    normalized = normalize_registration_email(email)
    wait = _resend_wait_seconds(normalized, now)
    if wait > 0:
        return SendRegistrationCodeResult(
            ok=False,
            message=OTP_RESEND_COOLDOWN_MESSAGE,
            error_code=OTP_RESEND_COOLDOWN_CODE,
            server_time=now,
            resend_available_in_seconds=wait,
        )

    code = _generate_code()
    expires_at = now + timedelta(minutes=_CODE_TTL_MINUTES)
    expires_in_seconds = int((expires_at - now).total_seconds())

    # Invalidate any previous unverified OTP for this email.
    EmailRegistrationVerification.objects.filter(
        email__iexact=normalized,
        verified_at__isnull=True,
    ).delete()

    EmailRegistrationVerification.objects.create(
        email=normalized,
        code_hash=_hash_code(code),
        expires_at=expires_at,
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
        # Never log the OTP itself.
        logger.exception("Failed to send verification email: %s", type(exc).__name__)
        return SendRegistrationCodeResult(
            ok=False,
            message="تعذر إرسال رمز التحقق. حاول مرة أخرى لاحقًا.",
            server_time=now,
        )

    return SendRegistrationCodeResult(
        ok=True,
        expires_at=expires_at,
        expires_in_seconds=expires_in_seconds,
        server_time=now,
        resend_available_in_seconds=_RESEND_COOLDOWN_SECONDS,
    )


def send_registration_code_payload(result: SendRegistrationCodeResult) -> dict:
    """JSON-safe payload (never includes the OTP)."""
    payload: dict = {
        "success": result.ok,
        "server_time": _iso(result.server_time or timezone.now()),
    }
    if result.message:
        payload["message"] = result.message
    if result.error_code:
        payload["code"] = result.error_code
    if result.expires_at is not None:
        payload["expires_at"] = _iso(result.expires_at)
    if result.expires_in_seconds is not None:
        payload["expires_in_seconds"] = result.expires_in_seconds
    if result.resend_available_in_seconds is not None:
        payload["resend_available_in_seconds"] = result.resend_available_in_seconds
    return payload


def verify_registration_code(
    email: str, code: str
) -> tuple[str | None, str | None, str | None]:
    """Verify OTP once and issue a registration-session token (not the OTP).

    Returns (token, error_message, error_code).
    """
    normalized = (email or "").strip().lower()
    raw_code = (code or "").strip()
    if not normalized or len(raw_code) != 4 or not raw_code.isdigit():
        return None, OTP_INVALID_MESSAGE, None

    record = (
        EmailRegistrationVerification.objects.filter(
            email__iexact=normalized,
            verified_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if record is None:
        return None, OTP_INVALID_MESSAGE, None

    if record.expires_at < timezone.now():
        return None, OTP_EXPIRED_MESSAGE, OTP_EXPIRED_CODE

    if record.code_hash != _hash_code(raw_code):
        return None, OTP_INVALID_MESSAGE, None

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
    return token, None, None


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
