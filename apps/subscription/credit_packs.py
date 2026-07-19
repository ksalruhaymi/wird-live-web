"""Minute credit pack lifecycle: create, expire, aggregate, deduct."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.subscription.models import (
    MinuteCreditPack,
    StudentSubscription,
    StudentSubscriptionBalance,
    SubscriptionPlan,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
BILLING_QUANT = Decimal("0.0001")


def _minutes(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def plan_is_open_ended(plan: SubscriptionPlan) -> bool:
    """Open packs: both validity fields null (legacy: duration_months <= 0)."""
    value = getattr(plan, "validity_value", None)
    unit = (getattr(plan, "validity_unit", None) or "").strip() or None
    if value is not None or unit is not None:
        return False
    # Both validity fields empty: open unless legacy duration_months says timed.
    return int(getattr(plan, "duration_months", 0) or 0) <= 0


def compute_pack_expires_at(*, plan: SubscriptionPlan, purchased_at=None) -> date | None:
    """Compute pack expiry from validity_value/unit (calendar months, not 30-day)."""
    if plan_is_open_ended(plan):
        return None

    purchased_day = timezone.localdate()
    if purchased_at is not None:
        purchased_day = timezone.localtime(purchased_at).date()

    value = getattr(plan, "validity_value", None)
    unit = (getattr(plan, "validity_unit", None) or "").strip() or None

    if value is not None and unit == SubscriptionPlan.ValidityUnit.DAYS:
        return purchased_day + timedelta(days=int(value))
    if value is not None and unit == SubscriptionPlan.ValidityUnit.MONTHS:
        return purchased_day + relativedelta(months=int(value))

    # Legacy fallback: duration_months as calendar months.
    months = int(getattr(plan, "duration_months", 0) or 0)
    if months > 0:
        return purchased_day + relativedelta(months=months)
    return None


def expire_stale_packs_for_user(user, *, today: date | None = None) -> int:
    """Mark timed packs past expires_at as expired. Returns rows updated."""
    today = today or timezone.localdate()
    return (
        MinuteCreditPack.objects.filter(
            user=user,
            status=MinuteCreditPack.Status.ACTIVE,
            expires_at__isnull=False,
            expires_at__lt=today,
        ).update(status=MinuteCreditPack.Status.EXPIRED, updated_at=timezone.now())
    )


def active_pack_queryset(user, *, today: date | None = None):
    """Active packs that still have minutes and are not past expiry."""
    today = today or timezone.localdate()
    expire_stale_packs_for_user(user, today=today)
    return (
        MinuteCreditPack.objects.filter(
            user=user,
            status=MinuteCreditPack.Status.ACTIVE,
            remaining_minutes__gt=ZERO,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=today))
        .order_by(
            # Timed packs first (nearest expiry), then open-ended (nulls last).
            F("expires_at").asc(nulls_last=True),
            "purchased_at",
            "id",
        )
    )


def available_minutes_for_user(user, *, today: date | None = None) -> Decimal:
    today = today or timezone.localdate()
    total = active_pack_queryset(user, today=today).aggregate(
        total=Sum("remaining_minutes")
    )["total"]
    return _minutes(total or ZERO)


def nearest_pack_expiry(user, *, today: date | None = None) -> date | None:
    """Earliest expires_at among active timed packs; None if only open packs."""
    pack = (
        active_pack_queryset(user, today=today)
        .filter(expires_at__isnull=False)
        .order_by("expires_at", "id")
        .first()
    )
    return pack.expires_at if pack else None


@transaction.atomic
def sync_wallet_from_packs(user) -> StudentSubscriptionBalance:
    """Refresh StudentSubscriptionBalance cache from active packs."""
    today = timezone.localdate()
    expire_stale_packs_for_user(user, today=today)
    available = available_minutes_for_user(user, today=today)
    nearest = nearest_pack_expiry(user, today=today)

    balance, _ = StudentSubscriptionBalance.objects.select_for_update().get_or_create(
        user=user,
        defaults={
            "status": StudentSubscriptionBalance.Status.EXPIRED,
            "remaining_minutes": ZERO,
        },
    )
    balance.remaining_minutes = available
    # Display expiry: nearest timed pack; null if only open packs (or none).
    has_open = active_pack_queryset(user, today=today).filter(expires_at__isnull=True).exists()
    if nearest is not None:
        balance.expires_at = nearest
    elif has_open and available > ZERO:
        # Open packs only — sentinel far date so legacy is_balance_active works,
        # OR we update is_balance_active. Prefer updating balance status by minutes.
        balance.expires_at = None
    else:
        balance.expires_at = nearest

    if available > ZERO:
        balance.status = StudentSubscriptionBalance.Status.ACTIVE
        # When only open packs, keep expires_at null and rely on pack-aware active check.
        if has_open and nearest is None:
            balance.expires_at = None
    else:
        balance.status = StudentSubscriptionBalance.Status.EXPIRED

    latest = (
        MinuteCreditPack.objects.filter(user=user)
        .order_by("-purchased_at", "-id")
        .first()
    )
    if latest:
        balance.current_plan_title = latest.plan_title or balance.current_plan_title
        balance.last_purchase_at = latest.purchased_at

    balance.save()
    return balance


def find_pack_by_store_transaction(transaction_id: str) -> MinuteCreditPack | None:
    tx = (transaction_id or "").strip()
    if not tx:
        return None
    return MinuteCreditPack.objects.filter(store_transaction_id=tx).first()


@transaction.atomic
def create_minute_credit_pack(
    *,
    user,
    plan: SubscriptionPlan,
    store: str,
    store_product_id: str = "",
    store_transaction_id: str = "",
    purchase_token: str = "",
    google_consume_pending: bool = False,
    student_subscription: StudentSubscription | None = None,
) -> MinuteCreditPack:
    """Create a pack after verification (or free/complimentary). Idempotent on store tx."""
    tx = (store_transaction_id or "").strip()
    if tx:
        existing = (
            MinuteCreditPack.objects.select_for_update()
            .filter(store_transaction_id=tx)
            .first()
        )
        if existing is not None:
            return existing

    now = timezone.now()
    minutes = _minutes(plan.minutes)
    pack = MinuteCreditPack.objects.create(
        user=user,
        plan=plan,
        plan_title=plan.title,
        purchased_minutes=minutes,
        remaining_minutes=minutes,
        purchased_at=now,
        expires_at=compute_pack_expires_at(plan=plan, purchased_at=now),
        store=(store or "").strip(),
        store_product_id=(store_product_id or "").strip(),
        store_transaction_id=tx,
        purchase_token=(purchase_token or "").strip(),
        status=MinuteCreditPack.Status.ACTIVE,
        google_consume_pending=bool(google_consume_pending),
        student_subscription=student_subscription,
    )
    sync_wallet_from_packs(user)
    return pack


@transaction.atomic
def deduct_minutes_from_packs(user, amount: Decimal) -> Decimal:
    """
    Deduct billable minutes across packs.
    Order: nearest expires_at first, then open-ended packs.
    Returns amount actually deducted.
    """
    need = _minutes(amount)
    if need <= ZERO:
        return ZERO

    today = timezone.localdate()
    deducted = ZERO
    packs = list(
        active_pack_queryset(user, today=today).select_for_update()
    )
    for pack in packs:
        if deducted >= need:
            break
        available = _minutes(pack.remaining_minutes)
        if available <= ZERO:
            pack.status = MinuteCreditPack.Status.EXHAUSTED
            pack.save(update_fields=["status", "updated_at"])
            continue
        take = min(available, need - deducted)
        pack.remaining_minutes = available - take
        deducted += take
        if pack.remaining_minutes <= ZERO:
            pack.remaining_minutes = ZERO
            pack.status = MinuteCreditPack.Status.EXHAUSTED
        pack.save(
            update_fields=["remaining_minutes", "status", "updated_at"]
        )

    sync_wallet_from_packs(user)
    return deducted.quantize(BILLING_QUANT)


def retry_pending_google_consumes(*, limit: int = 50) -> int:
    """Safely retry Google consume for packs that still need it."""
    from apps.subscription.store_verification.catalog import PRODUCT_KIND_CONSUMABLE
    from apps.subscription.store_verification.google import consume_google_purchase
    from apps.subscription.store_verification.types import VerifiedStorePurchase

    pending = list(
        MinuteCreditPack.objects.filter(
            google_consume_pending=True,
            store="play_store",
        ).order_by("id")[:limit]
    )
    done = 0
    for pack in pending:
        if not pack.purchase_token or not pack.store_product_id:
            continue
        verified = VerifiedStorePurchase(
            payment_method="play_store",
            product_id=pack.store_product_id,
            transaction_id=pack.store_transaction_id or str(pack.id),
            environment="sandbox",  # consume API does not need env
            product_kind=PRODUCT_KIND_CONSUMABLE,
            package_or_bundle_id="",
            minutes=int(pack.purchased_minutes),
            needs_google_consume=True,
            google_purchase_token=pack.purchase_token,
        )
        try:
            consume_google_purchase(verified)
            MinuteCreditPack.objects.filter(pk=pack.pk).update(
                google_consume_pending=False,
                updated_at=timezone.now(),
            )
            done += 1
        except Exception:  # noqa: BLE001
            logger.exception("Retry Google consume failed for pack=%s", pack.pk)
    return done
