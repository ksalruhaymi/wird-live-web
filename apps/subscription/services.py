from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from identity.accounts.user_types import USER_TYPE_STUDENT, resolve_user_type_slug

from .models import StudentSubscription, SubscriptionPlan

User = get_user_model()

CALL_INELIGIBLE_MESSAGE = (
    "يجب أن يكون لديك اشتراك فعال ورصيد كافٍ للاتصال بالمعلم."
)
STUDENT_ONLY_SUBSCRIPTION_MESSAGE = "الاشتراكات متاحة للطلاب فقط."


def add_months(start: date, months: int) -> date:
    """Add calendar months to a date."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    # Last day of target month caps the day (e.g. Jan 31 + 1 month -> Feb 28/29).
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


def student_can_request_call(user) -> tuple[bool, str]:
    """Return (allowed, message). Balance ledger not implemented yet."""
    if not is_student_user(user):
        return False, "هذا الإجراء للطلاب فقط."
    sub = get_current_active_subscription(user)
    if not sub:
        return False, CALL_INELIGIBLE_MESSAGE
    return True, ""


def call_eligibility_payload(user) -> dict:
    if not is_student_user(user):
        return {
            "success": True,
            "applicable": False,
            "can_call": False,
            "has_active_subscription": False,
            "balance": None,
            "message": "",
        }

    can_call, message = student_can_request_call(user)
    sub = get_current_active_subscription(user)
    return {
        "success": True,
        "applicable": True,
        "can_call": can_call,
        "has_active_subscription": sub is not None,
        # Per-call credit balance is not implemented; subscription gate only.
        "balance": None,
        "message": message,
    }


def get_current_active_subscription(user) -> StudentSubscription | None:
    """Latest paid active subscription that has not ended yet."""
    today = timezone.localdate()
    candidates = (
        StudentSubscription.objects.filter(
            user=user,
            payment_status=StudentSubscription.PaymentStatus.PAID,
            status=StudentSubscription.Status.ACTIVE,
            end_date__gte=today,
        )
        .select_related("plan", "user")
        .order_by("-end_date", "-id")
    )
    for sub in candidates:
        if display_status(sub, today=today) == StudentSubscription.DisplayStatus.ACTIVE:
            return sub
    return None


def subscription_to_payload(sub: StudentSubscription, *, include_display: bool = False) -> dict:
    payload = {
        "id": sub.id,
        "plan_title": sub.plan_title,
        "duration_months": sub.duration_months,
        "amount": str(sub.amount),
        "start_date": sub.start_date.isoformat(),
        "end_date": sub.end_date.isoformat(),
        "status": sub.status,
        "payment_status": sub.payment_status,
        "payment_method": sub.payment_method or "",
        "transaction_reference": sub.transaction_reference or "",
        "created_at": sub.created_at.isoformat(),
    }
    if include_display:
        payload["display_status"] = display_status(sub)
    return payload


def current_subscription_payload(user) -> dict:
    if not is_student_user(user):
        return {
            "success": True,
            "applicable": False,
            "has_active_subscription": False,
            "can_call": False,
            "message": STUDENT_ONLY_SUBSCRIPTION_MESSAGE,
        }

    sub = get_current_active_subscription(user)
    can_call, _ = student_can_request_call(user)
    if not sub:
        return {
            "success": True,
            "applicable": True,
            "has_active_subscription": False,
            "can_call": False,
            "balance": None,
            "message": "",
        }
    return {
        "success": True,
        "applicable": True,
        "has_active_subscription": True,
        "can_call": can_call,
        "balance": None,
        "plan_title": sub.plan_title,
        "duration_months": sub.duration_months,
        "amount": str(sub.amount),
        "start_date": sub.start_date.isoformat(),
        "end_date": sub.end_date.isoformat(),
        "status": sub.status,
        "message": "",
    }


@transaction.atomic
def create_student_subscription(
    user,
    *,
    plan_id: int,
    payment_method: str = "manual",
) -> tuple[StudentSubscription | None, str | None]:
    """Create a paid manual subscription from a plan. Returns (subscription, error_message)."""
    if not is_student_user(user):
        return None, STUDENT_ONLY_SUBSCRIPTION_MESSAGE

    try:
        plan = SubscriptionPlan.objects.get(pk=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return None, "الباقة غير موجودة."

    if not plan.is_active:
        return None, "الباقة غير متاحة."

    start = timezone.localdate()
    end = add_months(start, plan.duration_months)

    sub = StudentSubscription.objects.create(
        user=user,
        plan=plan,
        plan_title=plan.title,
        duration_months=plan.duration_months,
        amount=plan.price,
        start_date=start,
        end_date=end,
        status=StudentSubscription.Status.ACTIVE,
        payment_status=StudentSubscription.PaymentStatus.PAID,
        payment_method=payment_method or "manual",
    )
    return sub, None
