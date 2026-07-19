from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    resolve_user_type_slug,
)

from .models import StudentSubscription, StudentSubscriptionBalance, SubscriptionPlan

User = get_user_model()

CALL_INELIGIBLE_MESSAGE = (
    "يجب أن يكون لديك اشتراك فعال ورصيد كافٍ للاتصال بالمعلم."
)
STUDENT_ONLY_SUBSCRIPTION_MESSAGE = "الاشتراكات متاحة للطلاب فقط."

BILLING_MINUTE_QUANT = Decimal("0.0001")
ZERO_MINUTES = Decimal("0")
LOW_MINUTES_THRESHOLD = Decimal("5")
LOW_MINUTES_MESSAGE = "باقي لديك 5 دقائق اتصال فقط"
EXPIRED_MINUTES_MESSAGE = "لقد انتهت دقائق اتصالك"
LOW_MINUTES_NOTIFICATION_TITLE = "تنبيه الدقائق"


def add_months(start: date, months: int) -> date:
    """Add calendar months to a date."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    from calendar import monthrange

    max_day = monthrange(year, month)[1]
    day = min(start.day, max_day)
    return date(year, month, day)


def display_status(subscription: StudentSubscription, *, today: date | None = None) -> str:
    """Computed status for UI: active, expired, or cancelled."""
    today = today or timezone.localdate()
    if subscription.status == StudentSubscription.Status.CANCELLED:
        return StudentSubscription.DisplayStatus.CANCELLED
    if subscription.end_date < today:
        return StudentSubscription.DisplayStatus.EXPIRED
    if (
        subscription.status == StudentSubscription.Status.ACTIVE
        and subscription.end_date >= today
    ):
        return StudentSubscription.DisplayStatus.ACTIVE
    return StudentSubscription.DisplayStatus.EXPIRED


def balance_display_status(
    balance: StudentSubscriptionBalance,
    *,
    today: date | None = None,
) -> str:
    """Computed status for the user's current balance summary."""
    today = today or timezone.localdate()
    if balance.status == StudentSubscriptionBalance.Status.CANCELLED:
        return StudentSubscription.DisplayStatus.CANCELLED
    if not balance.expires_at or balance.expires_at < today:
        return StudentSubscription.DisplayStatus.EXPIRED
    if balance.status == StudentSubscriptionBalance.Status.ACTIVE:
        return StudentSubscription.DisplayStatus.ACTIVE
    return StudentSubscription.DisplayStatus.EXPIRED


def display_status_label(display: str) -> str:
    return {
        StudentSubscription.DisplayStatus.ACTIVE: "ساري",
        StudentSubscription.DisplayStatus.EXPIRED: "منتهي",
        StudentSubscription.DisplayStatus.CANCELLED: "ملغي",
    }.get(display, display)


def is_student_user(user) -> bool:
    if getattr(user, "user_type", None) == USER_TYPE_STUDENT:
        return True
    return resolve_user_type_slug(user) == "student"


def is_admin_user(user) -> bool:
    if getattr(user, "user_type", None) == USER_TYPE_ADMIN:
        return True
    if getattr(user, "is_superuser", False):
        return True
    if resolve_user_type_slug(user) == "admin":
        return True
    roles = getattr(user, "roles", None)
    if roles is not None and roles.filter(slug="admin").exists():
        return True
    return False


def can_use_subscription_packages(user) -> bool:
    if is_student_user(user) or is_admin_user(user):
        return True
    if hasattr(user, "has_permission"):
        return user.has_permission("mobile.subscriptions.checkout.create")
    return False


def get_user_subscription_balance(user) -> StudentSubscriptionBalance | None:
    try:
        return StudentSubscriptionBalance.objects.get(user=user)
    except StudentSubscriptionBalance.DoesNotExist:
        return None


def is_balance_active(balance: StudentSubscriptionBalance, *, today: date | None = None) -> bool:
    today = today or timezone.localdate()
    return balance_display_status(balance, today=today) == StudentSubscription.DisplayStatus.ACTIVE


def get_current_active_subscription(user) -> StudentSubscription | None:
    """Return latest paid history row when the user has an active balance."""
    balance = get_user_subscription_balance(user)
    if not balance or not is_balance_active(balance):
        return None
    return (
        StudentSubscription.objects.filter(
            user=user,
            payment_status=StudentSubscription.PaymentStatus.PAID,
        )
        .select_related("plan", "user")
        .order_by("-created_at", "-id")
        .first()
    )


def sync_balance_status_from_expiry(
    balance: StudentSubscriptionBalance,
    *,
    today: date | None = None,
) -> None:
    """Keep stored status aligned with expiry after admin edits."""
    today = today or timezone.localdate()
    if balance.status == StudentSubscriptionBalance.Status.CANCELLED:
        return
    display = balance_display_status(balance, today=today)
    if display == StudentSubscription.DisplayStatus.EXPIRED:
        balance.status = StudentSubscriptionBalance.Status.EXPIRED
    elif display == StudentSubscription.DisplayStatus.ACTIVE:
        balance.status = StudentSubscriptionBalance.Status.ACTIVE


def _minutes_value(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _serialize_minutes(value: Decimal | int | None) -> float | None:
    if value is None:
        return None
    return float(_minutes_value(value).quantize(BILLING_MINUTE_QUANT))


def subscription_minutes_flags(
    balance: StudentSubscriptionBalance | None,
) -> dict:
    """Computed minute status for API payloads (no side effects)."""
    if balance is None:
        return {
            "remaining_minutes": 0,
            "low_minutes_warning": False,
            "minutes_expired": False,
            "low_minutes_message": "",
            "expired_message": "",
        }

    remaining = _minutes_value(balance.remaining_minutes)
    remaining_f = _serialize_minutes(remaining) or 0
    active = is_balance_active(balance)
    low = active and ZERO_MINUTES < remaining <= LOW_MINUTES_THRESHOLD
    expired = active and remaining <= ZERO_MINUTES

    return {
        "remaining_minutes": remaining_f,
        "low_minutes_warning": low,
        "minutes_expired": expired,
        "low_minutes_message": LOW_MINUTES_MESSAGE if low else "",
        "expired_message": EXPIRED_MINUTES_MESSAGE if expired else "",
    }


def _merge_minutes_flags(payload: dict, balance: StudentSubscriptionBalance | None) -> dict:
    payload.update(subscription_minutes_flags(balance))
    return payload


def maybe_send_low_minutes_notification(
    user,
    balance: StudentSubscriptionBalance,
) -> None:
    """Create one in-app warning per balance cycle when minutes drop to threshold."""
    if not is_balance_active(balance):
        return
    remaining = _minutes_value(balance.remaining_minutes)
    if remaining <= ZERO_MINUTES or remaining > LOW_MINUTES_THRESHOLD:
        return
    if balance.low_minutes_warning_sent_at is not None:
        return

    from apps.notification.models import (
        Notification,
        NotificationChannel,
        NotificationLevel,
    )

    Notification.objects.create(
        user=user,
        title=LOW_MINUTES_NOTIFICATION_TITLE,
        message=LOW_MINUTES_MESSAGE,
        channel=NotificationChannel.IN_APP,
        level=NotificationLevel.WARNING,
    )
    balance.low_minutes_warning_sent_at = timezone.now()
    balance.save(update_fields=["low_minutes_warning_sent_at", "updated_at"])


def sync_low_minutes_notification(user, balance: StudentSubscriptionBalance | None) -> None:
    """Ensure warning exists when API/subscription state is read after threshold."""
    if balance is None:
        return
    maybe_send_low_minutes_notification(user, balance)


def student_can_request_call(user) -> tuple[bool, str]:
    if not can_use_subscription_packages(user):
        return False, "هذا الإجراء للطلاب فقط."
    balance = get_user_subscription_balance(user)
    if not balance or not is_balance_active(balance):
        return False, CALL_INELIGIBLE_MESSAGE
    if balance.remaining_minutes <= ZERO_MINUTES:
        return False, CALL_INELIGIBLE_MESSAGE
    return True, ""


def call_eligibility_payload(user) -> dict:
    if not can_use_subscription_packages(user):
        return {
            "success": True,
            "applicable": False,
            "can_call": False,
            "has_active_subscription": False,
            "balance": None,
            "message": "",
        }

    can_call, message = student_can_request_call(user)
    balance = get_user_subscription_balance(user)
    active = balance is not None and is_balance_active(balance)
    sync_low_minutes_notification(user, balance)
    return _merge_minutes_flags(
        {
            "success": True,
            "applicable": True,
            "can_call": can_call,
            "has_active_subscription": active,
            "balance": _serialize_minutes(balance.remaining_minutes if balance else None),
            "message": message,
        },
        balance,
    )


def subscription_to_payload(sub: StudentSubscription, *, include_display: bool = False) -> dict:
    payload = {
        "id": sub.id,
        "plan_title": sub.plan_title,
        "duration_months": sub.duration_months,
        "amount": str(sub.amount),
        "is_free": sub.is_free,
        "display_price": sub.display_price,
        "start_date": sub.start_date.isoformat(),
        "end_date": sub.end_date.isoformat(),
        "status": sub.status,
        "payment_status": sub.payment_status,
        "payment_method": sub.payment_method or "",
        "transaction_reference": sub.transaction_reference or "",
        "created_at": sub.created_at.isoformat(),
        "plan_minutes_added": sub.plan_minutes_added,
        "minutes_before": sub.minutes_before,
        "minutes_after": sub.minutes_after,
        "expiry_before": sub.expiry_before.isoformat() if sub.expiry_before else None,
        "expiry_after": sub.expiry_after.isoformat() if sub.expiry_after else None,
        "transaction_type": sub.transaction_type or "purchase",
    }
    if include_display:
        payload["display_status"] = display_status(sub)
    return payload


def current_subscription_payload(user) -> dict:
    if not can_use_subscription_packages(user):
        return {
            "success": True,
            "applicable": False,
            "has_active_subscription": False,
            "can_call": False,
            "message": "",
        }

    balance = get_user_subscription_balance(user)
    can_call, _ = student_can_request_call(user)
    sync_low_minutes_notification(user, balance)
    if not balance or not is_balance_active(balance):
        return _merge_minutes_flags(
            {
                "success": True,
                "applicable": True,
                "has_active_subscription": False,
                "can_call": False,
                "balance": _serialize_minutes(balance.remaining_minutes if balance else None),
                "remaining_minutes": _serialize_minutes(balance.remaining_minutes if balance else None) or 0,
                "used_minutes": _serialize_minutes(balance.used_minutes if balance else None) or 0,
                "message": "",
            },
            balance,
        )

    expires = balance.expires_at.isoformat() if balance.expires_at else ""
    return _merge_minutes_flags(
        {
            "success": True,
            "applicable": True,
            "has_active_subscription": True,
            "can_call": can_call,
            "balance": _serialize_minutes(balance.remaining_minutes),
            "remaining_minutes": _serialize_minutes(balance.remaining_minutes),
            "used_minutes": _serialize_minutes(balance.used_minutes),
            "plan_title": balance.current_plan_title,
            "package_title": balance.current_plan_title,
            "expires_at": expires,
            "end_date": expires,
            "status": balance.status,
            "message": "",
        },
        balance,
    )


@transaction.atomic
def create_student_subscription(
    user,
    *,
    plan_id: int,
    payment_method: str = "manual",
) -> tuple[StudentSubscription | None, str | None]:
    """Create a paid subscription purchase and update the user's active balance."""
    if not can_use_subscription_packages(user):
        return None, STUDENT_ONLY_SUBSCRIPTION_MESSAGE

    admin_complimentary = is_admin_user(user)

    try:
        plan = SubscriptionPlan.objects.get(pk=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return None, "الباقة غير موجودة."

    if not plan.is_active:
        return None, "الباقة غير متاحة."

    today = timezone.localdate()
    balance, _ = StudentSubscriptionBalance.objects.select_for_update().get_or_create(
        user=user,
        defaults={
            "status": StudentSubscriptionBalance.Status.EXPIRED,
            "remaining_minutes": ZERO_MINUTES,
        },
    )

    balance_active = is_balance_active(balance, today=today)
    minutes_before = balance.remaining_minutes
    expiry_before = balance.expires_at

    if balance_active and balance.expires_at:
        extend_from = balance.expires_at
        new_minutes = _minutes_value(balance.remaining_minutes) + Decimal(plan.minutes)
        transaction_type = "renewal"
        period_start = extend_from
    else:
        extend_from = today
        new_minutes = Decimal(plan.minutes)
        transaction_type = "purchase"
        period_start = today

    new_expires = add_months(extend_from, plan.duration_months)
    now = timezone.now()

    balance.current_plan_title = plan.title
    balance.remaining_minutes = new_minutes
    balance.expires_at = new_expires
    balance.status = StudentSubscriptionBalance.Status.ACTIVE
    balance.last_purchase_at = now
    balance.low_minutes_warning_sent_at = None
    balance.save()

    charge_amount = Decimal("0") if admin_complimentary else plan.price
    resolved_payment_method = (
        "complimentary"
        if admin_complimentary
        else (payment_method or "manual")
    )

    sub = StudentSubscription.objects.create(
        user=user,
        plan=plan,
        plan_title=plan.title,
        duration_months=plan.duration_months,
        amount=charge_amount,
        start_date=period_start,
        end_date=new_expires,
        status=StudentSubscription.Status.ACTIVE,
        payment_status=StudentSubscription.PaymentStatus.PAID,
        payment_method=resolved_payment_method,
        plan_minutes_added=plan.minutes,
        minutes_before=minutes_before,
        minutes_after=new_minutes,
        expiry_before=expiry_before,
        expiry_after=new_expires,
        transaction_type=transaction_type,
    )
    return sub, None


def call_billable_minutes(call) -> Decimal:
    """Billable minutes for an ended call (second-accurate, no rounding up)."""
    if not call.started_at or not call.ended_at:
        return ZERO_MINUTES
    seconds = max(0, int((call.ended_at - call.started_at).total_seconds()))
    if seconds <= 0:
        return ZERO_MINUTES
    return (Decimal(seconds) / Decimal("60")).quantize(
        BILLING_MINUTE_QUANT,
        rounding=ROUND_HALF_UP,
    )


def call_duration_minutes(call) -> Decimal:
    """Backward-compatible alias."""
    return call_billable_minutes(call)


@transaction.atomic
def deduct_call_minutes_for_session(call) -> Decimal:
    """
    Deduct used minutes from the student's subscription balance when a call ends.
    Returns minutes charged (0 if skipped or already charged).
    """
    from apps.calls.models import CallSession
    from apps.tutoring.teacher_services import is_demo_teacher

    if call.status != CallSession.Status.ENDED:
        return 0

    locked = CallSession.objects.select_for_update().get(pk=call.pk)
    if locked.minutes_charged is not None:
        return locked.minutes_charged

    if locked.is_interview_call:
        locked.minutes_charged = ZERO_MINUTES
        locked.save(update_fields=["minutes_charged", "updated_at"])
        return 0

    if getattr(locked, "is_test_call", False):
        locked.minutes_charged = ZERO_MINUTES
        locked.save(update_fields=["minutes_charged", "updated_at"])
        return 0

    teacher = locked.teacher
    if teacher is not None and is_demo_teacher(teacher):
        locked.minutes_charged = ZERO_MINUTES
        locked.save(update_fields=["minutes_charged", "updated_at"])
        return 0

    billable = call_billable_minutes(locked)
    if billable <= ZERO_MINUTES:
        locked.minutes_charged = ZERO_MINUTES
        locked.save(update_fields=["minutes_charged", "updated_at"])
        return ZERO_MINUTES

    if not can_use_subscription_packages(locked.student):
        locked.minutes_charged = ZERO_MINUTES
        locked.save(update_fields=["minutes_charged", "updated_at"])
        return 0

    balance = (
        StudentSubscriptionBalance.objects.select_for_update()
        .filter(user_id=locked.student_id)
        .first()
    )
    charge = ZERO_MINUTES
    if balance is not None:
        charge = min(billable, _minutes_value(balance.remaining_minutes))
        if charge > ZERO_MINUTES:
            balance.remaining_minutes = _minutes_value(balance.remaining_minutes) - charge
            balance.used_minutes = _minutes_value(balance.used_minutes) + charge
            balance.save(
                update_fields=["remaining_minutes", "used_minutes", "updated_at"]
            )
            maybe_send_low_minutes_notification(locked.student, balance)

    locked.minutes_charged = charge
    locked.save(update_fields=["minutes_charged", "updated_at"])
    return charge
