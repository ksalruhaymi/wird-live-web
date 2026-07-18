"""Rematch CallRecording.object_key to a playable final media file in R2.

Safe: lists objects under the recording prefix, picks mp4/m4a/aac/mp3,
updates DB only. Does not delete storage objects or re-record.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.calls.cloud_recording.service import try_finalize_recording_files
from apps.calls.models import CallRecording
from apps.calls.recording_storage import (
    find_playable_object_key_for_recording,
    is_playable_object_key,
    object_key_for_recording,
    prefix_for_recording_objects,
)


class Command(BaseCommand):
    help = (
        "Rematch a recording row to a playable R2 object (mp4 preferred). "
        "Dry-run by default; pass --apply to persist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "recording_id",
            nargs="?",
            type=int,
            help="CallRecording primary key (e.g. 76).",
        )
        parser.add_argument(
            "--call-id",
            type=int,
            default=None,
            help="Alternative: CallSession id (uses its recording row).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the rematched object key (default is dry-run).",
        )

    def handle(self, *args, **options):
        recording_id = options.get("recording_id")
        call_id = options.get("call_id")
        apply = bool(options.get("apply"))

        if recording_id:
            rec = CallRecording.objects.filter(pk=recording_id).select_related(
                "call_session"
            ).first()
            if rec is None:
                raise CommandError(f"CallRecording id={recording_id} not found.")
        elif call_id:
            rec = (
                CallRecording.objects.filter(call_session_id=call_id)
                .select_related("call_session")
                .first()
            )
            if rec is None:
                raise CommandError(f"No CallRecording for call_id={call_id}.")
        else:
            raise CommandError("Provide recording_id or --call-id.")

        before = object_key_for_recording(rec)
        prefix = prefix_for_recording_objects(rec)
        candidate = find_playable_object_key_for_recording(rec)

        self.stdout.write(f"recording_id={rec.id} call_id={rec.call_session_id}")
        self.stdout.write(f"status={rec.recording_status}")
        self.stdout.write(f"before_key={before or '<empty>'}")
        self.stdout.write(f"prefix={prefix or '<empty>'}")
        self.stdout.write(f"candidate={candidate or '<none>'}")
        self.stdout.write(f"before_playable={is_playable_object_key(before)}")
        self.stdout.write(
            f"candidate_playable={is_playable_object_key(candidate)}"
        )

        if not candidate:
            # Fall back to Agora finalize path (no deletes).
            if apply:
                ok = try_finalize_recording_files(rec, allow_expire=False)
                rec.refresh_from_db()
                after = object_key_for_recording(rec)
                self.stdout.write(f"finalize_ok={ok} after_key={after or '<empty>'}")
                if not is_playable_object_key(after):
                    raise CommandError(
                        "No playable media found under prefix; DB unchanged."
                    )
                self.stdout.write(self.style.SUCCESS("Rematched via finalize."))
                return
            raise CommandError(
                "No playable media found (dry-run). Check R2 prefix, then --apply."
            )

        if is_playable_object_key(before) and before == candidate:
            self.stdout.write(self.style.SUCCESS("Already playable; nothing to do."))
            return

        if not apply:
            self.stdout.write(
                self.style.WARNING("Dry-run only. Re-run with --apply to update DB.")
            )
            return

        ok = try_finalize_recording_files(rec, allow_expire=False)
        rec.refresh_from_db()
        after = object_key_for_recording(rec)
        self.stdout.write(f"after_key={after or '<empty>'}")
        self.stdout.write(f"after_status={rec.recording_status}")
        self.stdout.write(f"after_playable={rec.is_playable}")
        if not ok or not rec.is_playable:
            raise CommandError("Rematch did not produce a playable completed row.")
        self.stdout.write(self.style.SUCCESS("Rematch applied."))
