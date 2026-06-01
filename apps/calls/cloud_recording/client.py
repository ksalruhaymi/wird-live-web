"""Low-level Agora Cloud Recording REST client."""

from __future__ import annotations

import base64
import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

AGORA_RECORDING_API = "https://api.agora.io/v1/apps"


class AgoraCloudRecordingError(Exception):
    """Raised when Agora Cloud Recording API returns an error."""


class AgoraCloudRecordingClient:
    def __init__(self) -> None:
        self.app_id = (getattr(settings, "AGORA_APP_ID", "") or "").strip()
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
        json_body: dict | None = None,
        timeout: int = 30,
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
            raise AgoraCloudRecordingError("recording request failed") from exc

        if response.status_code >= 400:
            logger.warning(
                "Agora cloud recording HTTP %s on %s",
                response.status_code,
                path.split("?")[0],
            )
            raise AgoraCloudRecordingError(
                f"recording API returned status {response.status_code}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise AgoraCloudRecordingError("invalid recording API response") from exc

        if not isinstance(data, dict):
            raise AgoraCloudRecordingError("unexpected recording API response shape")
        return data

    def acquire(self, *, channel_name: str, recording_uid: str) -> str:
        data = self._request(
            "POST",
            "/cloud_recording/acquire",
            json_body={
                "cname": channel_name,
                "uid": recording_uid,
                "clientRequest": {},
            },
        )
        resource_id = (data.get("resourceId") or "").strip()
        if not resource_id:
            raise AgoraCloudRecordingError("acquire returned no resourceId")
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
        data = self._request(
            "POST",
            f"/cloud_recording/resourceid/{resource_id}/mode/{self.mode}/start",
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
        )
        sid = (data.get("sid") or "").strip()
        if not sid:
            raise AgoraCloudRecordingError("start returned no sid")
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
            json_body={
                "cname": channel_name,
                "uid": recording_uid,
                "clientRequest": {"async_stop": False},
            },
            timeout=60,
        )

    def query(self, *, resource_id: str, sid: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/cloud_recording/resourceid/{resource_id}/sid/{sid}/mode/{self.mode}/query",
            timeout=30,
        )


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

    # Vendor 11 (S3-compatible): Agora requires extensionParams.endpoint (e.g. Cloudflare R2).
    if endpoint:
        storage["extensionParams"] = {"endpoint": endpoint}

    return storage


def _recording_config(session_type: str) -> dict[str, Any]:
    is_video = (session_type or "").strip().lower() == "video"
    return {
        "channelType": 0,
        "streamTypes": 2 if is_video else 0,
        "maxIdleTime": 120,
        "subscribeUidGroup": 0,
    }
