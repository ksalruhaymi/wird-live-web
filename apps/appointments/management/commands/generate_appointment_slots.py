from django.core.management.base import BaseCommand

from apps.appointments.constants import SLOT_GENERATION_WINDOW_DAYS
from apps.appointments.services.slot_generation import generate_slots_for_all_teachers


class Command(BaseCommand):
    help = (
        "Idempotently generate/extend AppointmentSlot rows for active availability "
        f"rules within a {SLOT_GENERATION_WINDOW_DAYS}-day rolling window."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=SLOT_GENERATION_WINDOW_DAYS,
            help="Generation window in days (default 90).",
        )

    def handle(self, *args, **options):
        days = options["days"]
        results = generate_slots_for_all_teachers(window_days=days)
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {len(results)} teacher(s) for a {days}-day window."
            )
        )
        for row in results:
            self.stdout.write(
                f"  teacher={row['teacher_id']} candidates={row['candidates']} "
                f"expired={row['expired']} {row['window_start']}→{row['window_end']}"
            )
