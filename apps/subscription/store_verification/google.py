"""Google Play Billing verification + consume for minute consumables."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import google.auth.transport.requests
import requests
from django.conf import settings
from google.oauth2 import service_account

from apps.subscription.store_verification.catalog import (
    PRODUCT_KIND_CONSUMABLE,
    expected_product_id,
    minutes_from_product_id,
)
from apps.subscription.store_verification.types import (
    StoreVerificationError,
    VerifiedStorePurchase,
)

logger = logging.getLogger(__name__)

_ANDROID_PUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
_API_BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3"


def _package_name() -> str:
    return (
        getattr(settings, "GOOGLE_PLAY_PACKAGE_NAME", "") or "com.kslabs.wirdlive"
    ).strip()


def _service_account_path() -> str:
    return (getattr(settings, "GOOGLE_PLAY_SERVICE_ACCOUNT_PATH", "") or "").strip()


def _access_token() -> str:
    path = _service_account_path()
    if not path:
        raise StoreVerificationError(
            "إعدادات Google Play Developer API غير مكتملة "
            "(GOOGLE_PLAY_SERVICE_ACCOUNT_PATH)."
        )
    try:
        creds = service_account.Credentials.from_service_account_file(
            path,
            scopes=[_ANDROID_PUBLISHER_SCOPE],
        )
        creds.refresh(google.auth.transport.requests.Request())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load Google Play service account")
        raise StoreVerificationError(
            "تعذّر المصادقة مع Google Play Developer API."
        ) from exc
    if not creds.token:
        raise StoreVerificationError("تعذّر الحصول على رمز Google Play API.")
    return creds.token


def _request_json(
    method: str,
    url: str,
    *,
    access_token: str,
    body: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | None]:
    response = requests.request(
        method,
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=25,
    )
    if response.status_code == 204 or not response.content:
        return response.status_code, None
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        return response.status_code, data
    return response.status_code, None


def _purchase_environment(payload: dict[str, Any]) -> str:
    if payload.get("testPurchase") is not None:
        return "sandbox"
    if payload.get("purchaseType") == 0:
        return "sandbox"
    return "production"


def verify_google_purchase(
    *,
    minutes: int,
    purchase_token: str,
    store_product_id: str = "",
    expected_environment: str,
) -> VerifiedStorePurchase:
    """Verify a one-time consumable minute package via Play Developer API."""
    token = (purchase_token or "").strip()
    if not token:
        raise StoreVerificationError("رمز شراء Google Play (purchaseToken) مطلوب.")

    expected = expected_product_id(minutes=minutes, payment_method="play_store")
    product_id = (store_product_id or "").strip() or expected
    if product_id != expected:
        raise StoreVerificationError("معرّف منتج Google Play لا يطابق باقة الدقائق.")

    parsed_minutes = minutes_from_product_id(product_id)
    if parsed_minutes != int(minutes):
        raise StoreVerificationError("عدد دقائق منتج Google Play لا يطابق الباقة.")

    package_name = _package_name()
    access_token = _access_token()
    encoded_token = quote(token, safe="")
    url = (
        f"{_API_BASE}/applications/{package_name}/purchases/products/"
        f"{product_id}/tokens/{encoded_token}"
    )
    status, payload = _request_json("GET", url, access_token=access_token)
    if status == 404 or payload is None:
        raise StoreVerificationError("عملية شراء Google Play غير موجودة.")
    if status >= 400:
        raise StoreVerificationError(f"فشل التحقق من Google Play ({status}).")

    state = payload.get("purchaseState")
    if state == 1:
        raise StoreVerificationError("عملية شراء Google Play ملغاة.")
    if state == 2:
        raise StoreVerificationError("عملية شراء Google Play ما زالت معلّقة.")
    if state not in (0, None):
        raise StoreVerificationError("حالة شراء Google Play غير ناجحة.")

    # Consumables must not already be consumed (reuse protection at store level).
    if int(payload.get("consumptionState", 0) or 0) == 1:
        raise StoreVerificationError("عملية شراء Google Play مستهلكة مسبقاً.")

    needs_consume = True
    order_id = str(payload.get("orderId") or "").strip()
    if not order_id:
        raise StoreVerificationError("معرّف طلب Google Play مفقود.")

    environment = _purchase_environment(payload)
    if environment != expected_environment:
        raise StoreVerificationError(
            f"بيئة شراء Google ({environment}) لا تطابق بيئة الخادم ({expected_environment})."
        )

    return VerifiedStorePurchase(
        payment_method="play_store",
        product_id=product_id,
        transaction_id=order_id,
        environment=environment,
        product_kind=PRODUCT_KIND_CONSUMABLE,
        package_or_bundle_id=package_name,
        minutes=int(minutes),
        needs_google_consume=needs_consume,
        google_purchase_token=token,
        raw=payload,
    )


def consume_google_purchase(verified: VerifiedStorePurchase) -> None:
    """
    Consume a Google Play consumable after minutes were credited.

    Consume also satisfies acknowledge requirements for consumable products,
    and unlocks purchasing the same SKU again.
    """
    if verified.payment_method != "play_store":
        return
    if not verified.needs_google_consume:
        return
    token = (verified.google_purchase_token or "").strip()
    if not token:
        return

    package_name = verified.package_or_bundle_id or _package_name()
    access_token = _access_token()
    encoded_token = quote(token, safe="")
    product_id = verified.product_id
    url = (
        f"{_API_BASE}/applications/{package_name}/purchases/products/"
        f"{product_id}/tokens/{encoded_token}:consume"
    )
    status, _ = _request_json("POST", url, access_token=access_token, body={})
    if status not in {200, 204}:
        raise StoreVerificationError(f"فشل استهلاك شراء Google Play ({status}).")


# Backwards-compatible name used by older imports.
def acknowledge_google_purchase(verified: VerifiedStorePurchase) -> None:
    consume_google_purchase(verified)
