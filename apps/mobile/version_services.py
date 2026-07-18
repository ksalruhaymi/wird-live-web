"""Version comparison and update-decision helpers for mobile clients."""

from __future__ import annotations

import re
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.mobile.models import (
    BlockedMobileAppVersion,
    MobileAppConfig,
    MobileAppVersion,
    MobilePlatform,
    UpdateMode,
)

VERSION_NAME_RE = re.compile(r"^\d+(\.\d+){0,3}$")

ACTION_NO_UPDATE = "no_update"
ACTION_OPTIONAL = "optional_update"
ACTION_REQUIRED = "required_update"
ACTION_BLOCKED = "blocked_version"


def is_valid_version_name(value: str) -> bool:
    return bool(VERSION_NAME_RE.match((value or "").strip()))


def compare_semantic_versions(left: str, right: str) -> int:
    """Return negative when left < right, 0 when equal, positive when left > right."""
    left_parts = _parse_version_parts(left)
    right_parts = _parse_version_parts(right)
    length = max(len(left_parts), len(right_parts))
    for index in range(length):
        left_value = left_parts[index] if index < len(left_parts) else 0
        right_value = right_parts[index] if index < len(right_parts) else 0
        if left_value != right_value:
            return left_value - right_value
    return 0


def _parse_version_parts(raw: str) -> list[int]:
    cleaned = (raw or "").split("+", 1)[0].strip()
    if not cleaned:
        return [0]
    parts: list[int] = []
    for part in cleaned.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return parts or [0]


def normalize_locale(locale: str | None) -> str:
    value = (locale or "").strip().lower()
    if value.startswith("en"):
        return "en"
    return "ar"


def _pick_localized(ar: str, en: str, locale: str) -> str:
    if locale == "en":
        text = (en or "").strip() or (ar or "").strip()
    else:
        text = (ar or "").strip() or (en or "").strip()
    return text


def get_active_version(platform: str) -> MobileAppVersion | None:
    return (
        MobileAppVersion.objects.filter(platform=platform, is_active=True)
        .order_by("-activated_at", "-id")
        .first()
    )


def is_build_blocked(platform: str, build_number: int) -> BlockedMobileAppVersion | None:
    return (
        BlockedMobileAppVersion.objects.filter(
            platform=platform,
            build_number=build_number,
            is_active=True,
        )
        .order_by("-id")
        .first()
    )


def _has_started(starts_at: datetime | None, now: datetime) -> bool:
    if starts_at is None:
        return True
    return starts_at <= now


@transaction.atomic
def activate_mobile_app_version(
    version: MobileAppVersion,
    *,
    actor=None,
) -> MobileAppVersion:
    """Activate one version and deactivate other active rows for the same platform."""
    now = timezone.now()
    previous = (
        MobileAppVersion.objects.select_for_update()
        .filter(platform=version.platform, is_active=True)
        .exclude(pk=version.pk)
    )
    for row in previous:
        row.is_active = False
        row.deactivated_at = now
        if actor is not None:
            row.updated_by = actor
        row.save(
            update_fields=[
                "is_active",
                "deactivated_at",
                "updated_by",
                "updated_at",
            ]
        )

    version.is_active = True
    version.activated_at = now
    version.deactivated_at = None
    if actor is not None:
        version.updated_by = actor
    version.save()

    sync_active_version_to_legacy_config(version)
    return version


@transaction.atomic
def deactivate_mobile_app_version(
    version: MobileAppVersion,
    *,
    actor=None,
) -> MobileAppVersion:
    now = timezone.now()
    version.is_active = False
    version.deactivated_at = now
    if actor is not None:
        version.updated_by = actor
    version.save(
        update_fields=["is_active", "deactivated_at", "updated_by", "updated_at"]
    )
    return version


def sync_active_version_to_legacy_config(version: MobileAppVersion) -> None:
    """Keep MobileAppConfig in sync so middleware/old clients stay consistent."""
    config = MobileAppConfig.get_settings()
    min_version = (version.minimum_version_name or "").strip() or version.version_name
    min_build = version.minimum_build_number or 1
    config.min_supported_version = min_version
    config.min_supported_build = min_build
    config.force_update = version.update_mode == UpdateMode.REQUIRED
    message = (version.update_message_ar or "").strip()
    if message:
        config.message = message
    if version.store_url:
        config.update_url = version.store_url
    config.save(
        update_fields=[
            "min_supported_version",
            "min_supported_build",
            "force_update",
            "message",
            "update_url",
            "updated_at",
        ]
    )


def evaluate_app_version_check(
    *,
    platform: str,
    version_name: str,
    build_number: int,
    locale: str = "ar",
) -> dict:
    """
    Decide update action for a client.

    Priority:
    1. blocked_version
    2. required_update (below minimum build)
    3. required_update (update_mode required + older than latest)
    4. optional_update
    5. no_update
    """
    locale = normalize_locale(locale)
    platform = (platform or "").strip().lower()
    version_name = (version_name or "").strip()
    now = timezone.now()

    active = get_active_version(platform)
    latest_version_name = active.version_name if active else version_name
    latest_build = active.build_number if active else build_number

    blocked = is_build_blocked(platform, build_number)
    if blocked is not None:
        title = _pick_localized(
            "هذا الإصدار متوقف",
            "This Version Is No Longer Supported",
            locale,
        )
        message = _pick_localized(
            blocked.reason_ar
            or "يرجى تحديث التطبيق إلى أحدث إصدار للمتابعة.",
            blocked.reason_en
            or "Please update the app to the latest version to continue.",
            locale,
        )
        store_url = (active.store_url if active else "") or ""
        return {
            "success": True,
            "action": ACTION_BLOCKED,
            "update_available": True,
            "update_required": True,
            "blocked": True,
            "latest_version_name": latest_version_name,
            "latest_build_number": latest_build,
            "title": title,
            "message": message,
            "store_url": store_url,
            "allow_later": False,
            "later_reminder_hours": None,
        }

    if active is None or not _has_started(active.starts_at, now):
        return {
            "success": True,
            "action": ACTION_NO_UPDATE,
            "update_available": False,
            "update_required": False,
            "blocked": False,
            "latest_version_name": latest_version_name,
            "latest_build_number": latest_build,
        }

    # Current build is equal or newer than published latest.
    if build_number >= active.build_number:
        return {
            "success": True,
            "action": ACTION_NO_UPDATE,
            "update_available": False,
            "update_required": False,
            "blocked": False,
            "latest_version_name": active.version_name,
            "latest_build_number": active.build_number,
        }

    min_build = active.minimum_build_number
    below_minimum = min_build is not None and build_number < min_build

    title = _pick_localized(active.update_title_ar, active.update_title_en, locale)
    message = _pick_localized(
        active.update_message_ar, active.update_message_en, locale
    )
    release_notes = _pick_localized(
        active.release_notes_ar, active.release_notes_en, locale
    )

    if below_minimum or active.update_mode == UpdateMode.REQUIRED:
        if not title:
            title = _pick_localized(
                "يجب تحديث التطبيق",
                "Update Required",
                locale,
            )
        if not message:
            message = _pick_localized(
                "هذا الإصدار لم يعد مدعومًا. حدّث التطبيق للمتابعة.",
                "This version is no longer supported. Please update to continue.",
                locale,
            )
        return {
            "success": True,
            "action": ACTION_REQUIRED,
            "update_available": True,
            "update_required": True,
            "blocked": False,
            "latest_version_name": active.version_name,
            "latest_build_number": active.build_number,
            "minimum_version_name": active.minimum_version_name or active.version_name,
            "minimum_build_number": active.minimum_build_number,
            "title": title,
            "message": message,
            "release_notes": release_notes,
            "store_url": active.store_url or "",
            "allow_later": False,
            "later_reminder_hours": None,
        }

    if active.update_mode == UpdateMode.OPTIONAL:
        if not title:
            title = _pick_localized(
                "يتوفر تحديث جديد",
                "A New Update Is Available",
                locale,
            )
        if not message:
            message = _pick_localized(
                "حدّث التطبيق للحصول على التحسينات الجديدة.",
                "Update the app to get the latest improvements.",
                locale,
            )
        allow_later = bool(active.allow_later)
        return {
            "success": True,
            "action": ACTION_OPTIONAL,
            "update_available": True,
            "update_required": False,
            "blocked": False,
            "latest_version_name": active.version_name,
            "latest_build_number": active.build_number,
            "minimum_version_name": active.minimum_version_name or "",
            "minimum_build_number": active.minimum_build_number,
            "title": title,
            "message": message,
            "release_notes": release_notes,
            "store_url": active.store_url or "",
            "allow_later": allow_later,
            "later_reminder_hours": active.later_reminder_hours if allow_later else None,
        }

    # update_mode = none and older than latest → no forced prompt
    return {
        "success": True,
        "action": ACTION_NO_UPDATE,
        "update_available": False,
        "update_required": False,
        "blocked": False,
        "latest_version_name": active.version_name,
        "latest_build_number": active.build_number,
    }
