"""Password reset via email OTP + one-time reset token."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from identity.accounts.auth.login_service import _complete_login, _resolve_user
from identity.accounts.models import PasswordResetCode

logger = logging.getLogger(__name__)

User = get_user_model()

CODE_TTL_MINUTES = 10
RESET_TOKEN_TTL_MINUTES = 10
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60
REQUEST_RATE_LIMIT_COUNT = 5
REQUEST_RATE_LIMIT_WINDOW_MINUTES = 60

GENERIC_REQUEST_MESSAGE = (
    "إذا كانت البيانات مرتبطة بحساب، فسيتم إرسال رمز التحقق إلى البريد المسجل."
)
GENERIC_CODE_ERROR = "رمز التحقق غير صالح أو منتهي الصلاحية."
GENERIC_TOKEN_ERROR = "رابط أو رمز إعادة التعيين غير صالح أو منتهي الصلاحية."
RESEND_TOO_SOON_MESSAGE = "يرجى الانتظار قبل إعادة إرسال الرمز."
RATE_LIMIT_MESSAGE = "تم تجاوز الحد المسموح من المحاولات. حاول لاحقًا."


def _hash_secret(value: str) -> str:
    """Hash OTP / reset token; never log the raw value."""
    material = f"{settings.SECRET_KEY}:password-reset:{value}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _generate_reset_token() -> str:
    return secrets.token_urlsafe(32)


def _normalize_identifier(identifier: str) -> str:
    return (identifier or "").strip()


def _user_has_usable_email(user) -> bool:
    email = (getattr(user, "email", None) or "").strip()
    return bool(email) and "@" in email


def _client_ip(request) -> str:
    if request is None:
        return ""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    return (request.META.get("REMOTE_ADDR") or "").strip()


def _invalidate_open_codes(user) -> None:
    now = timezone.now()
    PasswordResetCode.objects.filter(user=user, used_at__isnull=True).update(
        used_at=now,
        updated_at=now,
    )


def _is_rate_limited(user) -> bool:
    window_start = timezone.now() - timedelta(minutes=REQUEST_RATE_LIMIT_WINDOW_MINUTES)
    count = PasswordResetCode.objects.filter(
        user=user,
        created_at__gte=window_start,
    ).count()
    return count >= REQUEST_RATE_LIMIT_COUNT


def _send_code_email(email: str, code: str) -> None:
    send_mail(
        subject="رمز استعادة كلمة المرور - ورد لايف",
        message=(
            "رمز التحقق الخاص بك هو:\n\n"
            f"{code}\n\n"
            f"الرمز صالح لمدة {CODE_TTL_MINUTES} دقائق.\n"
            "إذا لم تطلب استعادة كلمة المرور، يمكنك تجاهل هذه الرسالة."
        ),
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )


def _send_password_changed_email(email: str) -> None:
    send_mail(
        subject="تم تحديث كلمة المرور - ورد لايف",
        message=(
            "تم تحديث كلمة المرور لحسابك بنجاح.\n\n"
            "إذا لم تقم بهذا الإجراء، يرجى التواصل مع الدعم فورًا."
        ),
        from_email=None,
        recipient_list=[email],
        fail_silently=False,
    )


def _create_and_send_code(user, *, invalidate_previous: bool = True) -> tuple[bool, str | None]:
    if not _user_has_usable_email(user):
        # Silent from caller's perspective when used via request/resend public APIs.
        return True, None

    if _is_rate_limited(user):
        return False, RATE_LIMIT_MESSAGE

    if invalidate_previous:
        _invalidate_open_codes(user)

    code = _generate_code()
    now = timezone.now()
    PasswordResetCode.objects.create(
        user=user,
        code_hash=_hash_secret(code),
        expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
        max_attempts=MAX_ATTEMPTS,
    )

    try:
        _send_code_email(user.email.strip(), code)
    except Exception as exc:
        logger.exception("Failed to send password-reset code email: %s", type(exc).__name__)
        return False, "تعذر إرسال رمز التحقق. حاول مرة أخرى لاحقًا."

    return True, None


def request_password_reset(identifier: str, *, request=None) -> tuple[bool, str]:
    """
    Always returns the same generic success message to avoid account enumeration.
    """
    _ = _client_ip(request)  # reserved for future IP-based limits / auditing
    value = _normalize_identifier(identifier)
    if not value:
        return False, "البريد الإلكتروني أو اسم المستخدم مطلوب."

    user = _resolve_user(value)
    if user is not None and _user_has_usable_email(user):
        ok, error = _create_and_send_code(user, invalidate_previous=True)
        if not ok and error == RATE_LIMIT_MESSAGE:
            # Still avoid revealing whether the account exists: return generic success
            # when rate-limited after prior sends, or return rate limit for UX when
            # the user clearly has an active flow. Prefer generic message.
            return True, GENERIC_REQUEST_MESSAGE
        if not ok and error and "تعذر إرسال" in error:
            return False, error

    return True, GENERIC_REQUEST_MESSAGE


def resend_password_reset_code(identifier: str, *, request=None) -> tuple[bool, str]:
    _ = request
    value = _normalize_identifier(identifier)
    if not value:
        return False, "البريد الإلكتروني أو اسم المستخدم مطلوب."

    user = _resolve_user(value)
    if user is None or not _user_has_usable_email(user):
        return True, GENERIC_REQUEST_MESSAGE

    latest = (
        PasswordResetCode.objects.filter(user=user)
        .order_by("-created_at")
        .first()
    )
    if latest is not None:
        elapsed = (timezone.now() - latest.created_at).total_seconds()
        if elapsed < RESEND_COOLDOWN_SECONDS:
            return False, RESEND_TOO_SOON_MESSAGE

    if _is_rate_limited(user):
        return True, GENERIC_REQUEST_MESSAGE

    ok, error = _create_and_send_code(user, invalidate_previous=True)
    if not ok and error and "تعذر إرسال" in error:
        return False, error

    return True, GENERIC_REQUEST_MESSAGE


def verify_password_reset_code(
    identifier: str,
    code: str,
) -> tuple[str | None, str | None]:
    value = _normalize_identifier(identifier)
    raw_code = (code or "").strip()
    if not value or len(raw_code) != 6 or not raw_code.isdigit():
        return None, GENERIC_CODE_ERROR

    user = _resolve_user(value)
    if user is None:
        return None, GENERIC_CODE_ERROR

    record = (
        PasswordResetCode.objects.filter(
            user=user,
            used_at__isnull=True,
            verified_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    if record is None:
        return None, GENERIC_CODE_ERROR

    now = timezone.now()
    if record.expires_at < now:
        record.used_at = now
        record.save(update_fields=["used_at", "updated_at"])
        return None, GENERIC_CODE_ERROR

    if record.attempts_count >= record.max_attempts:
        record.used_at = now
        record.save(update_fields=["used_at", "updated_at"])
        return None, GENERIC_CODE_ERROR

    if record.code_hash != _hash_secret(raw_code):
        record.attempts_count += 1
        fields = ["attempts_count", "updated_at"]
        if record.attempts_count >= record.max_attempts:
            record.used_at = now
            fields.append("used_at")
        record.save(update_fields=fields)
        return None, GENERIC_CODE_ERROR

    reset_token = _generate_reset_token()
    record.verified_at = now
    record.reset_token_hash = _hash_secret(reset_token)
    record.reset_token_expires_at = now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    record.save(
        update_fields=[
            "verified_at",
            "reset_token_hash",
            "reset_token_expires_at",
            "updated_at",
        ]
    )
    return reset_token, None


def confirm_password_reset(
    request,
    *,
    reset_token: str,
    new_password: str,
    new_password_confirmation: str,
) -> tuple[object | None, str | None]:
    raw_token = (reset_token or "").strip()
    password = new_password or ""
    confirmation = new_password_confirmation or ""

    if not raw_token:
        return None, GENERIC_TOKEN_ERROR
    if not password or not confirmation:
        return None, "كلمة المرور وتأكيدها مطلوبان."
    if password != confirmation:
        return None, "كلمتا المرور غير متطابقتين."

    token_hash = _hash_secret(raw_token)
    record = (
        PasswordResetCode.objects.select_related("user")
        .filter(
            reset_token_hash=token_hash,
            verified_at__isnull=False,
            used_at__isnull=True,
        )
        .order_by("-verified_at")
        .first()
    )
    if record is None:
        return None, GENERIC_TOKEN_ERROR

    now = timezone.now()
    if (
        not record.reset_token_expires_at
        or record.reset_token_expires_at < now
    ):
        record.used_at = now
        record.save(update_fields=["used_at", "updated_at"])
        return None, GENERIC_TOKEN_ERROR

    user = record.user
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        messages = [str(m) for m in exc.messages]
        return None, " ".join(messages) if messages else "كلمة المرور غير مقبولة."

    with transaction.atomic():
        user.set_password(password)
        user.save(update_fields=["password"])
        record.used_at = now
        record.save(update_fields=["used_at", "updated_at"])
        PasswordResetCode.objects.filter(user=user, used_at__isnull=True).exclude(
            pk=record.pk
        ).update(used_at=now, updated_at=now)

    _complete_login(request, user)

    email = (user.email or "").strip()
    if email and "@" in email:
        try:
            _send_password_changed_email(email)
        except Exception as exc:
            logger.exception(
                "Failed to send password-changed email: %s",
                type(exc).__name__,
            )

    return user, None
