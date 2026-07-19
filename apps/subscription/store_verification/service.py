"""Orchestrate App Store / Play consumable verification before crediting minutes."""

from __future__ import annotations

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.subscription.store_verification.apple import verify_apple_purchase
from apps.subscription.store_verification.google import (
    consume_google_purchase,
    verify_google_purchase,
)
from apps.subscription.store_verification.types import (
    StoreVerificationError,
    VerifiedStorePurchase,
)

logger = logging.getLogger(__name__)


def expected_store_environment() -> str:
    """sandbox | production — must match mobile STORE_ENV / license testers."""
    raw = (getattr(settings, "STORE_BILLING_ENV", "") or "sandbox").strip().lower()
    if raw in {"prod", "production"}:
        return "production"
    return "sandbox"


def verify_store_purchase(
    *,
    payment_method: str,
    minutes: int,
    purchase_token: str,
    store_product_id: str = "",
    transaction_reference: str = "",
) -> VerifiedStorePurchase:
    """
    Verify a consumable minute-package purchase with Apple / Google.

    Does not credit minutes. Raises StoreVerificationError on failure.
    Never treats a client-only transaction_reference as proof of payment.
    """
    method = (payment_method or "").strip().lower()
    expected_env = expected_store_environment()

    if int(minutes) <= 0:
        raise StoreVerificationError("عدد دقائق الباقة غير صالح.")

    if method == "app_store":
        return verify_apple_purchase(
            minutes=minutes,
            purchase_token=purchase_token,
            store_product_id=store_product_id,
            transaction_reference=transaction_reference,
            expected_environment=expected_env,
        )
    if method == "play_store":
        return verify_google_purchase(
            minutes=minutes,
            purchase_token=purchase_token,
            store_product_id=store_product_id,
            expected_environment=expected_env,
        )
    raise StoreVerificationError("طريقة الدفع عبر المتجر غير مدعومة.")


def consume_google_purchase_if_needed(verified: VerifiedStorePurchase) -> None:
    """Consume Google Play consumable after minutes were credited."""
    try:
        consume_google_purchase(verified)
    except StoreVerificationError as exc:
        logger.error(
            "Google Play consume failed for tx=%s: %s",
            verified.transaction_id,
            exc.message,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Google Play consume unexpected error for tx=%s",
            verified.transaction_id,
        )


def schedule_google_consume(
    verified: VerifiedStorePurchase,
    *,
    pack_id: int | None = None,
) -> None:
    """Run consume after DB commit; clear pending only on success (safe to retry)."""
    if not verified.needs_google_consume:
        return

    def _run() -> None:
        try:
            consume_google_purchase(verified)
        except StoreVerificationError as exc:
            logger.error(
                "Google Play consume failed for tx=%s: %s",
                verified.transaction_id,
                exc.message,
            )
            return
        except Exception:  # noqa: BLE001
            logger.exception(
                "Google Play consume unexpected error for tx=%s",
                verified.transaction_id,
            )
            return
        if pack_id is not None:
            try:
                from apps.subscription.models import MinuteCreditPack

                MinuteCreditPack.objects.filter(pk=pack_id).update(
                    google_consume_pending=False,
                    updated_at=timezone.now(),
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed clearing google_consume_pending pack=%s", pack_id
                )

    transaction.on_commit(_run)


# Backwards-compatible aliases.
acknowledge_google_purchase_if_needed = consume_google_purchase_if_needed
schedule_google_acknowledge = schedule_google_consume
