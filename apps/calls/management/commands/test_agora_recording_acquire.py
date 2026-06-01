"""Call Agora Cloud Recording acquire only (safe diagnostics, no secrets printed)."""

from __future__ import annotations

import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.calls.cloud_recording.client import (
    AgoraCloudRecordingClient,
    AgoraCloudRecordingError,
    build_acquire_payload,
)


class Command(BaseCommand):
    help = (
        "Test Agora Cloud Recording acquire for a channel (REST auth + payload only)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--channel",
            default="test_channel",
            help="Channel name (cname) sent to acquire.",
        )
        parser.add_argument(
            "--uid",
            default="",
            help="Recording UID string (default: AGORA_RECORDING_UID from settings).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print acquire payload only; do not call Agora.",
        )

    def handle(self, *args, **options):
        channel = (options["channel"] or "").strip()
        uid = (options["uid"] or "").strip() or str(
            int(getattr(settings, "AGORA_RECORDING_UID", 900000001) or 900000001)
        )

        if not (getattr(settings, "AGORA_APP_ID", "") or "").strip():
            raise CommandError("AGORA_APP_ID is missing.")
        if not (getattr(settings, "AGORA_CUSTOMER_ID", "") or "").strip():
            raise CommandError("AGORA_CUSTOMER_ID is missing (REST API Key).")
        if not (getattr(settings, "AGORA_CUSTOMER_SECRET", "") or "").strip():
            raise CommandError("AGORA_CUSTOMER_SECRET is missing (REST API Secret).")

        payload = build_acquire_payload(channel_name=channel, recording_uid=uid)
        self.stdout.write("Acquire payload shape (no secrets):")
        self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=True))
        self.stdout.write(
            f"\nREST URL: POST /v1/apps/<app_id>/cloud_recording/acquire"
        )
        self.stdout.write(
            "Auth: Basic (AGORA_CUSTOMER_ID:AGORA_CUSTOMER_SECRET) — "
            "must be REST API Key/Secret, not App Certificate."
        )
        app_id = (settings.AGORA_APP_ID or "").strip()
        self.stdout.write(f"App ID suffix: ...{app_id[-4:] if len(app_id) >= 4 else '****'}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("\nDry run — Agora not called."))
            return

        client = AgoraCloudRecordingClient()
        try:
            resource_id = client.acquire(channel_name=channel, recording_uid=uid)
        except AgoraCloudRecordingError as exc:
            self.stdout.write(self.style.ERROR(f"\nAcquire failed: {exc}"))
            if exc.status_code is not None:
                self.stdout.write(f"HTTP status: {exc.status_code}")
            if exc.action:
                self.stdout.write(f"Action: {exc.action}")
            if exc.safe_body:
                self.stdout.write(f"Safe response body: {exc.safe_body}")
            raise CommandError("acquire failed") from exc

        self.stdout.write(self.style.SUCCESS(f"\nAcquire OK — resourceId present (len={len(resource_id)})"))
