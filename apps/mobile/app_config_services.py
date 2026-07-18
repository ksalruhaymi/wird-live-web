from __future__ import annotations

from apps.mobile.models import MobileAppConfig
from apps.mobile.version_services import compare_semantic_versions

__all__ = [
    "app_config_to_payload",
    "compare_semantic_versions",
    "build_mobile_access_denial",
    "evaluate_mobile_api_access",
]


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

    return None
