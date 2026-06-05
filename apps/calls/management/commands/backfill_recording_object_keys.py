"""Backfill CallRecording.recording_object_key from legacy recording_url values."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.calls.models import CallRecording
from apps.calls.recording_storage import object_key_from_public_url


class Command(BaseCommand):
    help = (
        "Populate recording_object_key from legacy recording_url values. "
        "Does not expose or modify public URLs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report rows that would be updated without saving.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        updated = 0
        skipped_has_key = 0
        skipped_no_key = 0

        qs = CallRecording.objects.exclude(recording_url="").order_by("id")
        for rec in qs.iterator():
            if (rec.recording_object_key or "").strip():
                skipped_has_key += 1
                continue

            key = object_key_from_public_url(rec.recording_url)
            if not key:
                skipped_no_key += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  recording {rec.id}: could not derive object key"
                    )
                )
                continue

            if dry_run:
                self.stdout.write(
                    f"  would set recording {rec.id} -> {key}"
                )
            else:
                rec.recording_object_key = key
                rec.save(update_fields=["recording_object_key"])
            updated += 1

        prefix = "Would update" if dry_run else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix} {updated} row(s); "
                f"skipped {skipped_has_key} with existing key; "
                f"skipped {skipped_no_key} without derivable key."
            )
        )
