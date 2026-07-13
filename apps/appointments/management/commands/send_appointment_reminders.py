from django.core.management.base import BaseCommand

from apps.appointments.services.call_link import (
    expire_missed_appointments,
    process_due_reminders,
)


class Command(BaseCommand):
    help = (
        "Send due appointment reminders (24h / 1h / 10m) and expire missed "
        "appointments. Safe to run every 1–5 minutes via cron."
    )

    def handle(self, *args, **options):
        sent = process_due_reminders()
        expired = expire_missed_appointments()
        self.stdout.write(
            self.style.SUCCESS(
                f"reminders 24h={sent['24h']} 1h={sent['1h']} 10m={sent['10m']} "
                f"expired={expired}"
            )
        )
