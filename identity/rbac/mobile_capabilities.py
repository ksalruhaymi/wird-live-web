"""Mobile capability flags derived from RBAC permissions for profile API payloads."""

from __future__ import annotations

from typing import Any

# Nested capability key -> permission code. Structure is fixed for every user.
MOBILE_CAPABILITY_PERMISSIONS: dict[str, dict[str, str]] = {
    "nav": {
        "home": "mobile.nav.home.view",
        "teachers": "mobile.nav.teachers.view",
        "recordings": "mobile.nav.recordings.view",
        "management": "mobile.nav.management.view",
        "settings": "mobile.nav.settings.view",
        "subscriptions": "mobile.nav.subscriptions.view",
    },
    "management": {
        "view_pending_teachers": "mobile.management.teachers.view",
        "approve_teachers": "mobile.management.teachers.approve",
        "reject_teachers": "mobile.management.teachers.reject",
        "interview_call": "mobile.management.teachers.interview_call",
    },
    "teachers": {
        "list": "mobile.teachers.list.view",
        "profile": "mobile.teachers.profile.view",
        "favorite_toggle": "mobile.teachers.favorite.toggle",
    },
    "subscriptions": {
        "packages": "mobile.subscriptions.packages.view",
        "status": "mobile.subscriptions.status.view",
        "checkout": "mobile.subscriptions.checkout.create",
    },
    "calls": {
        "request": "mobile.calls.request",
        "incoming": "mobile.calls.incoming.view",
        "accept": "mobile.calls.accept",
        "reject": "mobile.calls.reject",
    },
    "teacher": {
        "home": "mobile.teacher.home.view",
        "availability_update": "mobile.teacher.availability.update",
        "heartbeat": "mobile.teacher.heartbeat.send",
    },
    "recordings": {
        "list_own": "mobile.recordings.list_own.view",
        "play_own": "shared.recordings.play_own",
        "play_all": "shared.recordings.play_all",
        "download_own": "shared.recordings.download_own",
        "download_all": "shared.recordings.download_all",
    },
    "profile": {
        "view": "shared.profile.view",
        "update": "shared.profile.update",
        "avatar_update": "shared.profile.avatar.update",
    },
    "evaluations": {
        "submit": "mobile.evaluations.submit",
    },
}


def _empty_capabilities() -> dict[str, dict[str, bool]]:
    return {
        group: {key: False for key in keys}
        for group, keys in MOBILE_CAPABILITY_PERMISSIONS.items()
    }


def build_mobile_capabilities(user) -> dict[str, Any]:
    """Return nested capability booleans evaluated via user.has_permission()."""
    capabilities = _empty_capabilities()
    for group, keys in MOBILE_CAPABILITY_PERMISSIONS.items():
        for key, permission_code in keys.items():
            capabilities[group][key] = user.has_permission(permission_code)
    return capabilities
