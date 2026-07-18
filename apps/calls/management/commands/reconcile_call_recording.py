from django.core.management.base import BaseCommand, CommandError

from apps.calls.cloud_recording.reconcile import (
    inspect_call_recording,
    reconcile_call_recording,
)


class Command(BaseCommand):
    help = "Inspect or reconcile a single call recording (no secrets)."

    def add_arguments(self, parser):
        parser.add_argument("call_id", type=int)
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply reconcile (default inspect / dry-run).",
        )
        parser.add_argument(
            "--inspect-only",
            action="store_true",
            help="Only print inspection details.",
        )

    def handle(self, *args, **options):
        call_id = options["call_id"]
        if options["inspect_only"] or not options["apply"]:
            info = inspect_call_recording(call_id)
            if not info.get("ok"):
                raise CommandError(info.get("error", "inspect_failed"))
            self.stdout.write(self.style.NOTICE(str(info)))
            if not options["apply"]:
                self.stdout.write(
                    self.style.WARNING(
                        "Dry-run only. Re-run with --apply to reconcile."
                    )
                )
                return

        result = reconcile_call_recording(call_id, apply=True)
        self.stdout.write(self.style.SUCCESS(str(result)))
