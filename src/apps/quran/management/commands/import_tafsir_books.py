import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from apps.quran.models import TafsirBook


class Command(BaseCommand):
    help = "Import TafsirBook from CSV"

    def handle(self, *args, **kwargs):
        file_path = Path("apps/quran/data/tafsir.csv")

        with file_path.open(encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                TafsirBook.objects.update_or_create(
                    number=row["number"],
                    defaults={
                        "name": row["name"],
                        "lang": row["lang"],
                        "api": row["api"],
                        "image": row["image"],
                        "author": row["author"],
                        "info": row["info"],
                    },
                )

        self.stdout.write(self.style.SUCCESS("Tafsir books imported successfully"))