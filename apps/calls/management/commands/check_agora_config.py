"""Report Agora / cloud recording configuration status (no secret values printed)."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.calls.cloud_recording.client import _storage_config
from apps.calls.cloud_recording.service import cloud_recording_configured
from apps.calls.token_builder import (
    agora_credentials_configured,
    build_agora_rtc_token,
    is_production_environment,
    provider_name_for_new_call,
)
from apps.calls.models import CallSession


def _is_set(name: str) -> bool:
    value = getattr(settings, name, None)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, int):
        return True
    return bool(value)


class Command(BaseCommand):
    help = "Check Agora RTC and cloud recording env configuration (secrets not printed)."

    SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "Environment",
            ("APP_ENV", "DEBUG", "CALL_PROVIDER"),
        ),
        (
            "Agora Live Calls",
            (
                "AGORA_APP_ID",
                "AGORA_APP_CERTIFICATE",
                "CALL_TOKEN_TTL_SECONDS",
            ),
        ),
        (
            "Agora REST API",
            (
                "AGORA_CUSTOMER_ID",
                "AGORA_CUSTOMER_SECRET",
            ),
        ),
        (
            "Agora Cloud Recording",
            (
                "AGORA_RECORDING_FILE_PREFIX",
                "AGORA_RECORDING_UID",
                "AGORA_RECORDING_MODE",
                "AGORA_RECORDING_PUBLIC_BASE_URL",
            ),
        ),
        (
            "Cloudflare R2 / S3-compatible storage",
            (
                "AGORA_RECORDING_STORAGE_VENDOR",
                "AGORA_RECORDING_STORAGE_REGION",
                "AGORA_RECORDING_STORAGE_ENDPOINT",
                "AGORA_RECORDING_STORAGE_BUCKET",
                "AGORA_RECORDING_STORAGE_ACCESS_KEY",
                "AGORA_RECORDING_STORAGE_SECRET_KEY",
            ),
        ),
    )

    def handle(self, *args, **options):
        missing: list[str] = []
        for title, names in self.SECTIONS:
            self.stdout.write(f"\n=== {title} ===")
            for name in names:
                ok = _is_set(name)
                status = "present" if ok else "MISSING"
                self.stdout.write(f"  {name}: {status}")
                if not ok:
                    missing.append(name)

        self.stdout.write("\n=== Capability checks ===")
        self._check_rtc_tokens()
        self._check_provider_selection()
        self._check_cloud_recording_storage()
        self._check_production_safety()

        if missing:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{len(missing)} variable(s) missing or empty (see list above)."
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("\nAll listed variables are present."))

    def _check_rtc_tokens(self) -> None:
        if not agora_credentials_configured():
            self.stdout.write("  RTC tokens: unavailable (AGORA_APP_ID / CERTIFICATE missing)")
            return
        try:
            build_agora_rtc_token(channel_name="config_check", uid=900000001)
            self.stdout.write("  RTC tokens: OK (test token generated)")
        except Exception as exc:
            self.stdout.write(f"  RTC tokens: FAILED ({exc.__class__.__name__})")

    def _check_provider_selection(self) -> None:
        explicit = (getattr(settings, "CALL_PROVIDER", "") or "").strip().lower()
        try:
            provider = provider_name_for_new_call()
            self.stdout.write(
                f"  New call provider: {provider} (CALL_PROVIDER={explicit or 'auto'})"
            )
            if explicit == "agora" and provider != CallSession.Provider.AGORA:
                self.stdout.write(
                    self.style.WARNING(
                        "  CALL_PROVIDER=agora but provider resolved to non-Agora."
                    )
                )
        except Exception as exc:
            self.stdout.write(
                f"  New call provider: FAILED ({exc.__class__.__name__})"
            )

    def _check_cloud_recording_storage(self) -> None:
        if not cloud_recording_configured():
            self.stdout.write("  Cloud recording: not fully configured")
            return

        cfg = _storage_config("config_check")
        vendor = cfg.get("vendor")
        has_endpoint = bool(
            (cfg.get("extensionParams") or {}).get("endpoint")
        )
        self.stdout.write("  Cloud recording: configured")
        self.stdout.write(f"  storage vendor: {vendor}")
        if vendor == 11:
            self.stdout.write(
                f"  extensionParams.endpoint: {'present' if has_endpoint else 'MISSING'}"
            )

    def _check_production_safety(self) -> None:
        if not is_production_environment():
            self.stdout.write("  Production mock guard: skipped (APP_ENV is not prod)")
            return
        try:
            provider_name_for_new_call()
            self.stdout.write("  Production mock guard: OK (Agora path when configured)")
        except Exception:
            self.stdout.write(
                "  Production mock guard: OK (fails closed without Agora config)"
            )
        # Ensure mock tokens are never the production path when CALL_PROVIDER=agora
        if (getattr(settings, "CALL_PROVIDER", "") or "").strip().lower() == "mock":
            self.stdout.write(
                self.style.WARNING(
                    "  CALL_PROVIDER=mock in prod would be rejected at runtime."
                )
            )
