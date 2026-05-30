from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "تعطيل توكنات FCM النشطة التي لم تُستخدم منذ مدة محددة (افتراضي: 90 يوماً)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=90,
            help="عدد الأيام قبل اعتبار التوكن قديماً (افتراضي: 90)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض العدد دون تعطيل فعلي",
        )

    def handle(self, *args, **options):
        from apps.push.models import UserDevice

        days = options["days"]
        dry_run = options["dry_run"]

        cutoff = timezone.now() - timedelta(days=days)

        # التوكنات التي لم تُستخدم منذ cutoff أو التي لا تحتوي على last_seen_at
        qs = UserDevice.objects.filter(
            is_active=True,
            last_seen_at__lt=cutoff,
        )

        count = qs.count()

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"[DRY RUN] سيتم تعطيل {count} توكن (آخر ظهور قبل {days} يوماً أو أكثر)"
                )
            )
            return

        if count == 0:
            self.stdout.write(self.style.SUCCESS("لا توجد توكنات قديمة لتعطيلها."))
            return

        qs.update(is_active=False)

        self.stdout.write(
            self.style.SUCCESS(
                f"تم تعطيل {count} توكن لم يُستخدم منذ {days} يوماً أو أكثر."
            )
        )
