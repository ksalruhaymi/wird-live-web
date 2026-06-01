"""Low-level Agora Cloud Recording REST client."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

AGORA_RECORDING_API = "https://api.agora.io/v1/apps"

# REST auth uses AGORA_CUSTOMER_ID + AGORA_CUSTOMER_SECRET (Console → RESTful API),
# not AGORA_APP_ID / AGORA_APP_CERTIFICATE (RTC).

_SENSITIVE_JSON_KEYS = frozenset(
    {
        "token",
        "accesskey",
        "secretkey",
        "secret",
        "authorization",
        "password",
        "credential",
        "stsToken",
    }
)


class AgoraCloudRecordingError(Exception):
    """Raised when Agora Cloud Recording API returns an error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        action: str | None = None,
        safe_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.action = action
        self.safe_body = safe_body


class AgoraCloudRecordingClient:
    def __init__(self) -> None:
        self.app_id = (getattr(settings, "AGORA_APP_ID", "") or "").strip()
        # RESTful API Key / Secret (Basic Auth), not RTC certificate.
        self.customer_id = (getattr(settings, "AGORA_CUSTOMER_ID", "") or "").strip()
        self.customer_secret = (
            getattr(settings, "AGORA_CUSTOMER_SECRET", "") or ""
        ).strip()
        self.mode = (getattr(settings, "AGORA_RECORDING_MODE", "mix") or "mix").strip()

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(
            f"{self.customer_id}:{self.customer_secret}".encode()
        ).decode()
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        action: str,
        json_body: dict | None = None,
        timeout: int = 30,
        log_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{AGORA_RECORDING_API}/{self.app_id}{path}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            logger.warning(
                "Agora cloud recording request failed action=%s path=%s error=%s",
                action,
                path,
                exc.__class__.__name__,
                extra=_log_extra(log_context),
            )
            raise AgoraCloudRecordingError(
                "recording request failed",
                action=action,
            ) from exc

        if response.status_code >= 400:
            safe_body = _safe_response_body(response)
            logger.warning(
                "Agora cloud recording HTTP error action=%s path=%s status=%s "
                "app_id_suffix=%s body=%s %s",
                action,
                path,
                response.status_code,
                _app_id_suffix(self.app_id),
                safe_body,
                _format_log_context(log_context),
                extra=_log_extra(log_context),
            )
            detail = _error_detail_from_body(safe_body)
            message = f"recording API returned status {response.status_code}"
            if detail:
                message = f"{message}: {detail}"
            raise AgoraCloudRecordingError(
                message,
                status_code=response.status_code,
                action=action,
                safe_body=safe_body,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AgoraCloudRecordingError(
                "invalid recording API response",
                action=action,
            ) from exc

        if not isinstance(data, dict):
            raise AgoraCloudRecordingError(
                "unexpected recording API response shape",
                action=action,
            )
        return data

    def acquire(self, *, channel_name: str, recording_uid: str) -> str:
        payload = build_acquire_payload(
            channel_name=channel_name,
            recording_uid=recording_uid,
        )
        log_context = {
            "cname": channel_name,
            "uid": recording_uid,
            "resourceExpiredHour": payload["clientRequest"].get(
                "resourceExpiredHour"
            ),
        }
        data = self._request(
            "POST",
            "/cloud_recording/acquire",
            action="acquire",
            json_body=payload,
            log_context=log_context,
        )
        resource_id = (data.get("resourceId") or "").strip()
        if not resource_id:
            raise AgoraCloudRecordingError(
                "acquire returned no resourceId",
                action="acquire",
            )
        return resource_id

    def start(
        self,
        *,
        resource_id: str,
        channel_name: str,
        recording_uid: str,
        rtc_token: str,
        session_type: str,
    ) -> str:
        storage = _storage_config(channel_name)
        recording_config = _recording_config(session_type)
        recording_file_config = {
            "avFileType": ["hls", "mp4"],
        }
        log_context = {
            "cname": channel_name,
            "uid": recording_uid,
            "mode": self.mode,
            "storage_vendor": storage.get("vendor"),
            "storage_region": storage.get("region"),
            "storage_endpoint_set": bool(
                (storage.get("extensionParams") or {}).get("endpoint")
            ),
            "session_type": session_type,
        }
        data = self._request(
            "POST",
            f"/cloud_recording/resourceid/{resource_id}/mode/{self.mode}/start",
            action="start",
            json_body={
                "cname": channel_name,
                "uid": recording_uid,
                "clientRequest": {
                    "token": rtc_token,
                    "recordingConfig": recording_config,
                    "recordingFileConfig": recording_file_config,
                    "storageConfig": storage,
                },
            },
            timeout=45,
            log_context=log_context,
        )
        sid = (data.get("sid") or "").strip()
        if not sid:
            raise AgoraCloudRecordingError("start returned no sid", action="start")
        return sid

    def stop(
        self,
        *,
        resource_id: str,
        sid: str,
        channel_name: str,
        recording_uid: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/cloud_recording/resourceid/{resource_id}/sid/{sid}/mode/{self.mode}/stop",
            action="stop",
            json_body={
                "cname": channel_name,
                "uid": recording_uid,
                "clientRequest": {"async_stop": False},
            },
            timeout=60,
            log_context={"cname": channel_name, "uid": recording_uid, "sid": sid},
        )

    def query(self, *, resource_id: str, sid: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/cloud_recording/resourceid/{resource_id}/sid/{sid}/mode/{self.mode}/query",
            action="query",
            timeout=30,
            log_context={"sid": sid},
        )


def build_acquire_payload(
    *,
    channel_name: str,
    recording_uid: str,
) -> dict[str, Any]:
    """
    Agora acquire body:
    { "cname": "...", "uid": "<string>", "clientRequest": { "scene": 0, ... } }
    """
    cname = (channel_name or "").strip()
    if not cname:
        raise AgoraCloudRecordingError(
            "acquire requires non-empty cname",
            action="acquire",
        )
    if len(cname.encode("utf-8")) > 1024:
        raise AgoraCloudRecordingError(
            "acquire cname exceeds 1024 bytes",
            action="acquire",
        )

    uid_str = _normalize_recording_uid(recording_uid)
    expired_hour = int(
        getattr(settings, "AGORA_RECORDING_RESOURCE_EXPIRED_HOUR", 24) or 24
    )
    expired_hour = max(1, min(expired_hour, 720))

    return {
        "cname": cname,
        "uid": uid_str,
        "clientRequest": {
            "scene": 0,
            "resourceExpiredHour": expired_hour,
        },
    }


def _normalize_recording_uid(recording_uid: str | int) -> str:
    uid_str = str(recording_uid).strip()
    if not re.fullmatch(r"[0-9]+", uid_str):
        raise AgoraCloudRecordingError(
            "recording uid must be a numeric string",
            action="acquire",
        )
    uid_val = int(uid_str)
    if uid_val < 1 or uid_val > 4294967295:
        raise AgoraCloudRecordingError(
            "recording uid must be between 1 and 4294967295",
            action="acquire",
        )
    return uid_str


def _storage_config(channel_name: str) -> dict[str, Any]:
    prefix_raw = (getattr(settings, "AGORA_RECORDING_FILE_PREFIX", "") or "wird-live").strip()
    prefix_parts = [p for p in prefix_raw.replace("\\", "/").split("/") if p]
    prefix_parts.append(f"call_{channel_name}")

    vendor = int(getattr(settings, "AGORA_RECORDING_STORAGE_VENDOR", 0) or 0)
    endpoint = (
        getattr(settings, "AGORA_RECORDING_STORAGE_ENDPOINT", "") or ""
    ).strip().rstrip("/")

    storage: dict[str, Any] = {
        "vendor": vendor,
        "region": int(getattr(settings, "AGORA_RECORDING_STORAGE_REGION", 0) or 0),
        "bucket": (getattr(settings, "AGORA_RECORDING_STORAGE_BUCKET", "") or "").strip(),
        "accessKey": (
            getattr(settings, "AGORA_RECORDING_STORAGE_ACCESS_KEY", "") or ""
        ).strip(),
        "secretKey": (
            getattr(settings, "AGORA_RECORDING_STORAGE_SECRET_KEY", "") or ""
        ).strip(),
        "fileNamePrefix": prefix_parts,
    }

    if endpoint:
        storage["extensionParams"] = {"endpoint": endpoint}

    return storage


def _recording_config(session_type: str) -> dict[str, Any]:
    return {
        "channelType": 0,
        "streamTypes": 0,
        "maxIdleTime": 120,
        "subscribeUidGroup": 0,
    }


def _safe_response_body(response: requests.Response, max_len: int = 2000) -> str:
    text = (response.text or "").strip()
    if not text:
        return "(empty body)"
    try:
        parsed = json.loads(text)
    except ValueError:
        return _truncate(_redact_secrets_in_text(text), max_len)
    sanitized = _sanitize_json(parsed)
    return _truncate(json.dumps(sanitized, ensure_ascii=True), max_len)


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if str(key).lower() in _SENSITIVE_JSON_KEYS:
                out[key] = "***"
            else:
                out[key] = _sanitize_json(item)
        return out
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    return value


def _redact_secrets_in_text(text: str) -> str:
    # Redact long token-like strings if JSON parse failed.
    return re.sub(r'"(token|accessKey|secretKey)"\s*:\s*"[^"]+"', r'"\1":"***"', text)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _error_detail_from_body(safe_body: str) -> str:
    if not safe_body or safe_body == "(empty body)":
        return ""
    try:
        data = json.loads(safe_body)
    except ValueError:
        return safe_body[:200]
    if not isinstance(data, dict):
        return ""
    for key in ("reason", "message", "error", "errorMsg", "errMsg"):
        val = data.get(key)
        if val:
            return str(val)[:300]
    code = data.get("code")
    if code is not None:
        return f"code={code}"
    return ""


def _app_id_suffix(app_id: str) -> str:
    if len(app_id) < 8:
        return "****"
    return f"...{app_id[-4:]}"


def _format_log_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    parts = [f"{key}={value}" for key, value in context.items()]
    return "context[" + ", ".join(parts) + "]"


def _log_extra(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context:
        return {}
    return {"agora_recording_context": context}
