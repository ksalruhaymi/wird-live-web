"""Send Apple PushKit VoIP notifications via APNs HTTP/2.

Credentials come from env (never committed). If unset, callers skip VoIP
and rely on FCM for background (killed-state CallKit requires VoIP).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)


def _apns_configured() -> bool:
    team_id = (getattr(settings, "APNS_TEAM_ID", "") or "").strip()
    key_id = (getattr(settings, "APNS_KEY_ID", "") or "").strip()
    key = _load_private_key()
    return bool(team_id and key_id and key)


def _load_private_key() -> str:
    raw = (getattr(settings, "APNS_PRIVATE_KEY", "") or "").strip()
    if raw:
        return raw.replace("\\n", "\n")
    path = (getattr(settings, "APNS_PRIVATE_KEY_PATH", "") or "").strip()
    if not path:
        # Fall back to App Store Connect key if the same .p8 has APNs enabled.
        path = (getattr(settings, "APPLE_PRIVATE_KEY_PATH", "") or "").strip()
        raw = (getattr(settings, "APPLE_PRIVATE_KEY", "") or "").strip()
        if raw:
            return raw.replace("\\n", "\n")
    if path and Path(path).is_file():
        return Path(path).read_text(encoding="utf-8")
    return ""


def _jwt_token() -> str | None:
    import jwt

    team_id = (getattr(settings, "APNS_TEAM_ID", "") or "").strip()
    key_id = (
        (getattr(settings, "APNS_KEY_ID", "") or "").strip()
        or (getattr(settings, "APPLE_KEY_ID", "") or "").strip()
    )
    private_key = _load_private_key()
    if not team_id or not key_id or not private_key:
        return None
    now = int(time.time())
    return jwt.encode(
        {"iss": team_id, "iat": now},
        private_key,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id},
    )


def send_voip_push(device_token: str, data: dict[str, str]) -> bool:
    """Push a VoIP notification. Returns True on HTTP 200."""
    token = (device_token or "").strip()
    if not token:
        return False
    if not _apns_configured() and not _jwt_token():
        logger.info("APNs VoIP skipped — credentials not configured")
        return False

    auth = _jwt_token()
    if not auth:
        logger.warning("APNs VoIP JWT could not be built")
        return False

    bundle = (
        (getattr(settings, "APNS_BUNDLE_ID", "") or "").strip()
        or (getattr(settings, "APPLE_BUNDLE_ID", "") or "").strip()
        or "com.kslabs.wirdlive"
    )
    topic = f"{bundle}.voip"
    use_sandbox = bool(getattr(settings, "APNS_USE_SANDBOX", False))
    host = (
        "https://api.sandbox.push.apple.com"
        if use_sandbox
        else "https://api.push.apple.com"
    )
    url = f"{host}/3/device/{token}"

    # PushKit payload: custom keys only; system does not display VoIP as banner.
    body = {"aps": {"content-available": 1}, **data}

    headers = {
        "authorization": f"bearer {auth}",
        "apns-topic": topic,
        "apns-push-type": "voip",
        "apns-priority": "10",
        "apns-expiration": "0",
        "content-type": "application/json",
    }

    try:
        import httpx
    except ImportError:
        logger.error("httpx not installed — cannot send APNs VoIP push")
        return False

    try:
        with httpx.Client(http2=True, timeout=15.0) as client:
            response = client.post(url, headers=headers, content=json.dumps(body))
        if response.status_code == 200:
            logger.info("APNs VoIP sent ok token=%s…", token[:12])
            return True
        logger.warning(
            "APNs VoIP failed status=%s body=%s",
            response.status_code,
            response.text[:300],
        )
        return False
    except Exception:
        logger.exception("APNs VoIP send error")
        return False
