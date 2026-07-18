from django.core.management.base import BaseCommand, CommandError

from apps.calls.cloud_recording.reconcile import inspect_call_recording


class Command(BaseCommand):
    help = "Inspect call + recording status without secrets."

    def add_arguments(self, parser):
        parser.add_argument("call_id", type=int)

    def handle(self, *args, **options):
        info = inspect_call_recording(options["call_id"])
        if not info.get("ok"):
            raise CommandError(info.get("error", "inspect_failed"))
        self.stdout.write(self.style.NOTICE(str(info)))
