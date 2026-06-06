from __future__ import annotations

from apps.mobile.models import MobileAppConfig


def app_config_to_payload(config: MobileAppConfig) -> dict:
    """Public mobile app config payload (no sensitive fields)."""
    return {
        "app_enabled": config.app_enabled,
        "min_supported_version": config.min_supported_version,
        "min_supported_build": config.min_supported_build,
        "force_update": config.force_update,
        "message": config.message,
        "update_url": config.update_url or "",
    }


def compare_semantic_versions(left: str, right: str) -> int:
    """Return negative when left is lower than right."""
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
    return [int(part) if part.isdigit() else 0 for part in cleaned.split(".")]


def build_mobile_access_denial(
    *,
    status_code: int,
    code: str,
    config: MobileAppConfig,
) -> dict:
    return {
        "status_code": status_code,
        "payload": {
            "success": False,
            "code": code,
            "message": config.message,
            "update_url": config.update_url or "",
        },
    }


def evaluate_mobile_api_access(
    *,
    app_version: str,
    app_build: int,
    config: MobileAppConfig,
) -> dict | None:
    """Return denial metadata when the mobile client must be blocked."""
    if not config.app_enabled:
        return build_mobile_access_denial(
            status_code=403,
            code="app_disabled",
            config=config,
        )

    if app_build < config.min_supported_build:
        return build_mobile_access_denial(
            status_code=426,
            code="app_update_required",
            config=config,
        )

    if compare_semantic_versions(app_version, config.min_supported_version) < 0:
        return build_mobile_access_denial(
            status_code=426,
            code="app_update_required",
            config=config,
        )

    if config.force_update:
        return build_mobile_access_denial(
            status_code=426,
            code="app_update_required",
            config=config,
        )

    return None
