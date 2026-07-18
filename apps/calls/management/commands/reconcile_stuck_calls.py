from django.core.management.base import BaseCommand

from apps.calls.cloud_recording.reconcile import reconcile_stuck_calls


class Command(BaseCommand):
    help = "Reconcile stuck ACTIVE/ENDING calls and preparing recordings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes (default is dry-run).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Explicit dry-run (default).",
        )
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        dry_run = not options["apply"]
        summary = reconcile_stuck_calls(dry_run=dry_run, limit=options["limit"])
        self.stdout.write(self.style.NOTICE(str(summary)))
