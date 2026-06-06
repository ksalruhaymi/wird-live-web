import hashlib
import logging
import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

from identity.accounts.models import EmailRegistrationVerification

logger = logging.getLogger(__name__)

User = get_user_model()

_CODE_TTL_MINUTES = 10
_TOKEN_TTL_MINUTES = 30


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
    record.save(
        update_fields=["verified_at", "verification_token", "token_expires_at"],
    )
    return token, None


def consume_verification_token(email: str, token: str) -> bool:
    normalized = (email or "").strip().lower()
    raw_token = (token or "").strip()
    if not normalized or not raw_token:
        return False

    record = EmailRegistrationVerification.objects.filter(
        email__iexact=normalized,
        verification_token=raw_token,
        verified_at__isnull=False,
    ).first()
    if record is None:
        return False
    if record.token_expires_at and record.token_expires_at < timezone.now():
        return False
    record.delete()
    return True
