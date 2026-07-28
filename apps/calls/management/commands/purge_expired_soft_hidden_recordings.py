from django.core.management.base import BaseCommand

from apps.calls.recording_soft_delete import purge_expired_soft_hidden_recordings


class Command(BaseCommand):
    help = (
        "Hard-delete soft-hidden call recordings after both parties hide "
        "and the retention window (30 days) elapses."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply hard deletes (default is dry-run).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Explicit dry-run (default).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Max recordings to hard-delete in this run.",
        )

    def handle(self, *args, **options):
        dry_run = not options["apply"]
        summary = purge_expired_soft_hidden_recordings(
            limit=options["limit"],
            dry_run=dry_run,
        )
        self.stdout.write(self.style.NOTICE(str(summary)))
