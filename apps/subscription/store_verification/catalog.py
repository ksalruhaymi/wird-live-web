"""Canonical store product IDs for Wird Live minute packages (consumables)."""

from __future__ import annotations

IOS_PRODUCT_ID_PREFIX = "com.kslabs.wirdlive.minutes."
ANDROID_PRODUCT_ID_PREFIX = "wird_live_minutes_"

PRODUCT_KIND_CONSUMABLE = "consumable"


def ios_product_id_for_minutes(minutes: int) -> str:
    return f"{IOS_PRODUCT_ID_PREFIX}{int(minutes)}"


def android_product_id_for_minutes(minutes: int) -> str:
    return f"{ANDROID_PRODUCT_ID_PREFIX}{int(minutes)}"


def expected_product_id(*, minutes: int, payment_method: str) -> str:
    """Store SKU for a minute package (consumable / one-time consumable)."""
    method = (payment_method or "").strip().lower()
    mins = int(minutes)
    if mins <= 0:
        raise ValueError("minutes must be positive for store products")
    if method == "app_store":
        return ios_product_id_for_minutes(mins)
    if method == "play_store":
        return android_product_id_for_minutes(mins)
    raise ValueError(f"Unsupported payment_method for store product id: {payment_method}")


def minutes_from_product_id(product_id: str) -> int | None:
    """Parse minute count from a store product id, or null if unknown."""
    pid = (product_id or "").strip()
    if pid.startswith(IOS_PRODUCT_ID_PREFIX):
        try:
            value = int(pid[len(IOS_PRODUCT_ID_PREFIX) :])
        except ValueError:
            return None
        return value if value > 0 else None
    if pid.startswith(ANDROID_PRODUCT_ID_PREFIX):
        try:
            value = int(pid[len(ANDROID_PRODUCT_ID_PREFIX) :])
        except ValueError:
            return None
        return value if value > 0 else None
    return None
