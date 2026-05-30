from pathlib import Path
import csv

from django.core.management.base import BaseCommand
from apps.quran.models import Qurra


class Command(BaseCommand):
    help = "Import Qurra data from CSV file"

    def handle(self, *args, **options):
        base_dir = Path(__file__).resolve().parents[4]
        csv_path = base_dir / "apps" / "quran" / "data" / "qurra.csv"

        if not csv_path.exists():
            self.stderr.write(f"CSV file not found: {csv_path}")
            return

        with csv_path.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)

            for row in reader:
                Qurra.objects.update_or_create(
                    code=row["code"],  # 🔥 المفتاح الأساسي
                    defaults={
                        "name_ar": row["name_ar"],
                        "name_en": row["name_en"],
                        "image": row.get("image") or "",
                    },
                )

        self.stdout.write(self.style.SUCCESS("Qurra imported successfully."))