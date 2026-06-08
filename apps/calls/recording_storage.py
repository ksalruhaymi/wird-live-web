"""Private R2 recording object keys and presigned playback URLs."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

from apps.calls.models import CallRecording

logger = logging.getLogger(__name__)

KNOWN_PUBLIC_BASE_URLS = (
    "https://media.wird.me/",
    "https://recordings.wird.me/",
)


class RecordingStorageError(Exception):
    """Raised when a signed playback URL cannot be generated."""


def known_public_base_urls() -> tuple[str, ...]:
    """Return configured and legacy public bases used to build old recording URLs."""
    bases: list[str] = []
    configured = (getattr(settings, "AGORA_RECORDING_PUBLIC_BASE_URL", "") or "").strip()
    if configured:
        bases.append(configured if configured.endswith("/") else f"{configured}/")
    for base in KNOWN_PUBLIC_BASE_URLS:
        if base not in bases:
            bases.append(base)
    return tuple(bases)


def object_key_from_public_url(url: str) -> str:
    """Derive an R2 object key from a legacy public recording URL."""
    raw = (url or "").strip()
    if not raw:
        return ""

    # Drop query strings from presigned or cache-busted legacy URLs.
    raw = raw.split("?", 1)[0].strip()

    for base in known_public_base_urls():
        if raw.startswith(base):
            return raw[len(base) :].lstrip("/")

    parsed = urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.path:
        return parsed.path.lstrip("/")

    if not raw.startswith("http"):
        return raw.lstrip("/")

    return ""


def playback_content_type_for_key(object_key: str) -> str:
    """Return an HTML source type for the recorded object key."""
    name = (object_key or "").lower()
    if name.endswith(".m3u8"):
        return "application/vnd.apple.mpegurl"
    if name.endswith(".mp4"):
        return "audio/mp4"
    if name.endswith(".mp3"):
        return "audio/mpeg"
    return "audio/mp4"


def object_key_for_recording(recording: CallRecording) -> str:
    """Return the best available object key for a CallRecording row."""
    key = (recording.recording_object_key or "").strip()
    if key:
        return key
    return object_key_from_public_url(recording.recording_url or "")


def _get_r2_client():
    endpoint = (
        getattr(settings, "AGORA_RECORDING_STORAGE_ENDPOINT", "") or ""
    ).strip()
    access_key = (
        getattr(settings, "AGORA_RECORDING_STORAGE_ACCESS_KEY", "") or ""
    ).strip()
    secret_key = (
        getattr(settings, "AGORA_RECORDING_STORAGE_SECRET_KEY", "") or ""
    ).strip()
    if not endpoint or not access_key or not secret_key:
        raise RecordingStorageError("R2 storage credentials are not configured.")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def generate_recording_signed_url(object_key: str) -> tuple[str, int]:
    """Return a temporary GET URL and its expiry in seconds."""
    key = (object_key or "").strip()
    if not key:
        raise RecordingStorageError("Recording object key is missing.")

    bucket = (
        getattr(settings, "AGORA_RECORDING_STORAGE_BUCKET", "") or ""
    ).strip()
    if not bucket:
        raise RecordingStorageError("R2 bucket is not configured.")

    expires_in = int(
        getattr(settings, "RECORDING_SIGNED_URL_EXPIRES_SECONDS", 600) or 600
    )
    if expires_in < 60:
        expires_in = 60

    try:
        client = _get_r2_client()
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Failed to generate signed URL for key %s", key)
        raise RecordingStorageError("Could not generate signed playback URL.") from exc

    if not url:
        raise RecordingStorageError("Signed playback URL was empty.")

    return url, expires_in


def delete_recording_object(object_key: str) -> None:
    """Delete a recording object from R2. No-op when key is empty."""
    key = (object_key or "").strip()
    if not key:
        return

    bucket = (
        getattr(settings, "AGORA_RECORDING_STORAGE_BUCKET", "") or ""
    ).strip()
    if not bucket:
        raise RecordingStorageError("R2 bucket is not configured.")

    try:
        client = _get_r2_client()
        client.delete_object(Bucket=bucket, Key=key)
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Failed to delete R2 object for key %s", key)
        raise RecordingStorageError("Could not delete recording file from storage.") from exc


def user_can_access_recording(user, recording: CallRecording) -> bool:
    """Student/teacher party or dashboard user with recordings.view."""
    if not user or not user.is_authenticated:
        return False
    if recording.student_id == user.id or recording.teacher_id == user.id:
        return True
    try:
        call = getattr(recording, "call_session", None)
        if call is not None and hasattr(user, "has_permission"):
            if user.has_permission("management.teachers.view"):
                if getattr(call, "is_interview_call", False):
                    return True
                from identity.accounts.user_types import resolve_user_type_slug

                student = getattr(call, "student", None)
                if student and resolve_user_type_slug(student) in {
                    "admin",
                    "supervisor",
                }:
                    return True
    except Exception:
        # Fallback to standard permissions.
        pass
    if hasattr(user, "has_permission") and user.has_permission("recordings.view"):
        return True
    return False
