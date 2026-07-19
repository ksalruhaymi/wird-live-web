from __future__ import annotations

import logging
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

from .models import (
    MinuteCreditPack,
    StudentSubscription,
    StudentSubscriptionBalance,
    SubscriptionPlan,
)

User = get_user_model()
logger = logging.getLogger(__name__)

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
    """Computed status: active when spendable minute packs (or legacy wallet) remain."""
    today = today or timezone.localdate()
    if balance.status == StudentSubscriptionBalance.Status.CANCELLED:
        return StudentSubscription.DisplayStatus.CANCELLED

    from apps.subscription.credit_packs import available_minutes_for_user
    from apps.subscription.models import MinuteCreditPack

    if MinuteCreditPack.objects.filter(user_id=balance.user_id).exists():
        if available_minutes_for_user(balance.user, today=today) > ZERO_MINUTES:
            return StudentSubscription.DisplayStatus.ACTIVE
        return StudentSubscription.DisplayStatus.EXPIRED

    # Legacy single-wallet balances (no packs yet).
    if not balance.expires_at or balance.expires_at < today:
        return StudentSubscription.DisplayStatus.EXPIRED
    if (
        balance.status == StudentSubscriptionBalance.Status.ACTIVE
        and _minutes_value(balance.remaining_minutes) > ZERO_MINUTES
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


STORE_PAYMENT_METHODS = frozenset({"app_store", "play_store"})


@transaction.atomic
def create_student_subscription(
    user,
    *,
    plan_id: int,
    payment_method: str = "manual",
    transaction_reference: str = "",
    store_product_id: str = "",
    purchase_token: str = "",
    require_store_purchase: bool = False,
) -> tuple[StudentSubscription | None, str | None]:
    """Verify store purchase (when required), create a minute credit pack, sync wallet."""
    from apps.subscription.credit_packs import (
        available_minutes_for_user,
        compute_pack_expires_at,
        create_minute_credit_pack,
        find_pack_by_store_transaction,
        plan_is_open_ended,
        sync_wallet_from_packs,
    )

    if not can_use_subscription_packages(user):
        return None, STUDENT_ONLY_SUBSCRIPTION_MESSAGE

    admin_complimentary = is_admin_user(user)

    try:
        plan = SubscriptionPlan.objects.get(pk=plan_id)
    except SubscriptionPlan.DoesNotExist:
        return None, "الباقة غير موجودة."

    if not plan.is_active:
        return None, "الباقة غير متاحة."

    method = (payment_method or "manual").strip() or "manual"
    client_tx = (transaction_reference or "").strip()
    client_product_id = (store_product_id or "").strip()
    client_purchase_token = (purchase_token or "").strip()

    verified = None
    resolved_tx = client_tx
    resolved_product_id = client_product_id
    resolved_token = client_purchase_token

    if require_store_purchase and not admin_complimentary and not plan.is_free:
        if method not in STORE_PAYMENT_METHODS:
            return (
                None,
                "يجب إتمام الشراء عبر متجر التطبيقات (App Store / Google Play) أولاً.",
            )
        if not client_purchase_token:
            return (
                None,
                "بيانات التحقق من المتجر مطلوبة قبل تفعيل الاشتراك.",
            )
        try:
            from apps.subscription.store_verification import (
                StoreVerificationError,
                schedule_google_consume,
                verify_store_purchase,
            )

            verified = verify_store_purchase(
                payment_method=method,
                minutes=plan.minutes,
                purchase_token=client_purchase_token,
                store_product_id=client_product_id,
                transaction_reference=client_tx,
            )
        except StoreVerificationError as exc:
            return None, exc.message
        except Exception:
            logger.exception("Store purchase verification failed unexpectedly")
            return None, "تعذّر التحقق من عملية الشراء لدى المتجر."

        if verified.minutes != int(plan.minutes):
            return None, "عدد دقائق عملية المتجر لا يطابق الباقة."

        resolved_tx = verified.transaction_id
        resolved_product_id = verified.product_id
        method = verified.payment_method
        resolved_token = client_purchase_token

        existing_pack = find_pack_by_store_transaction(resolved_tx)
        if existing_pack is not None:
            if existing_pack.user_id != user.id:
                return None, "عملية الشراء مستخدمة مسبقاً على حساب آخر."
            if existing_pack.student_subscription_id:
                return existing_pack.student_subscription, None

        existing_sub = (
            StudentSubscription.objects.select_for_update()
            .filter(transaction_reference=resolved_tx)
            .order_by("-id")
            .first()
        )
        if existing_sub is not None:
            if existing_sub.user_id == user.id:
                return existing_sub, None
            return None, "عملية الشراء مستخدمة مسبقاً على حساب آخر."

    elif resolved_tx:
        existing = (
            StudentSubscription.objects.select_for_update()
            .filter(user=user, transaction_reference=resolved_tx)
            .order_by("-id")
            .first()
        )
        if existing is not None:
            return existing, None

    today = timezone.localdate()
    minutes_before = available_minutes_for_user(user, today=today)
    pack_expires = compute_pack_expires_at(plan=plan)
    period_start = today
    # Ledger end_date: pack expiry day, or start_date for open-ended packs.
    new_expires = pack_expires if pack_expires is not None else period_start
    transaction_type = "purchase"
    now = timezone.now()

    charge_amount = Decimal("0") if admin_complimentary else plan.price
    resolved_payment_method = (
        "complimentary" if admin_complimentary else method
    )
    stored_reference = resolved_tx
    if not stored_reference and resolved_product_id:
        stored_reference = resolved_product_id

    notes = ""
    if verified is not None:
        notes = (
            f"store_verified env={verified.environment} "
            f"kind={verified.product_kind} minutes={verified.minutes} "
            f"product={verified.product_id}"
        )
    if plan_is_open_ended(plan):
        notes = (notes + " open_ended=1").strip()

    minutes_after = minutes_before + Decimal(plan.minutes)

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
        transaction_reference=stored_reference or "",
        notes=notes,
        plan_minutes_added=plan.minutes,
        minutes_before=minutes_before,
        minutes_after=minutes_after,
        expiry_before=None,
        expiry_after=pack_expires,
        transaction_type=transaction_type,
    )

    needs_consume = bool(verified is not None and verified.needs_google_consume)
    pack = create_minute_credit_pack(
        user=user,
        plan=plan,
        store=resolved_payment_method if resolved_payment_method in STORE_PAYMENT_METHODS else (
            "complimentary" if admin_complimentary else "manual"
        ),
        store_product_id=resolved_product_id,
        store_transaction_id=stored_reference,
        purchase_token=resolved_token if verified is not None else "",
        google_consume_pending=needs_consume,
        student_subscription=sub,
    )
    sync_wallet_from_packs(user)
    balance = get_user_subscription_balance(user)
    if balance is not None:
        balance.low_minutes_warning_sent_at = None
        balance.last_purchase_at = now
        balance.save(
            update_fields=["low_minutes_warning_sent_at", "last_purchase_at", "updated_at"]
        )

    if needs_consume and verified is not None:
        from apps.subscription.store_verification import schedule_google_consume

        schedule_google_consume(verified, pack_id=pack.id)

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

    # Never bill calls that never reached Agora media-ready (setup failure).
    if not (
        getattr(locked, "student_media_ready_at", None)
        or getattr(locked, "teacher_media_ready_at", None)
        or getattr(locked, "participant_media_ready_at", None)
    ):
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
        from apps.subscription.credit_packs import deduct_minutes_from_packs
        from apps.subscription.models import MinuteCreditPack

        billable_left = billable
        if MinuteCreditPack.objects.filter(user_id=locked.student_id).exists():
            charge = deduct_minutes_from_packs(locked.student, billable_left)
            balance.refresh_from_db()
            balance.used_minutes = _minutes_value(balance.used_minutes) + charge
            balance.save(update_fields=["used_minutes", "updated_at"])
        else:
            # Legacy wallet without packs.
            charge = min(billable_left, _minutes_value(balance.remaining_minutes))
            if charge > ZERO_MINUTES:
                balance.remaining_minutes = (
                    _minutes_value(balance.remaining_minutes) - charge
                )
                balance.used_minutes = _minutes_value(balance.used_minutes) + charge
                balance.save(
                    update_fields=["remaining_minutes", "used_minutes", "updated_at"]
                )
        if charge > ZERO_MINUTES:
            maybe_send_low_minutes_notification(locked.student, balance)

    locked.minutes_charged = charge
    locked.save(update_fields=["minutes_charged", "updated_at"])
    return charge
