import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.quran.models import Ayah, AyahWordMeaning


class Command(BaseCommand):
    help = "Import ghareeb quran words from CSV into AyahWordMeaning table"

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            type=str,
            default="apps/quran/data/ayahwordmeaning.csv",
            help="Path to the CSV file",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete old records before importing",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = Path(options["csv"])

        if not csv_path.exists():
            self.stderr.write(self.style.ERROR(f"CSV file not found: {csv_path}"))
            return

        if options["clear"]:
            self.stdout.write("Deleting old AyahWordMeaning records...")
            AyahWordMeaning.objects.all().delete()

        self.stdout.write(f"Importing from: {csv_path}")

        created_count = 0
        updated_count = 0

        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            required_columns = {
                "surah_number",
                "ayah_number",
                "word",
                "word_plain",
                "meaning",
            }

            if not reader.fieldnames:
                self.stderr.write(self.style.ERROR("CSV file has no headers"))
                return

            missing_columns = required_columns - set(reader.fieldnames)
            if missing_columns:
                self.stderr.write(
                    self.style.ERROR(
                        f"Missing required columns: {', '.join(sorted(missing_columns))}"
                    )
                )
                return

            order_map = {}

            for row_number, row in enumerate(reader, start=2):
                try:
                    surah_number = int((row.get("surah_number") or "").strip())
                    ayah_number = int((row.get("ayah_number") or "").strip())
                    word = (row.get("word") or "").strip()
                    word_plain = (row.get("word_plain") or "").strip()
                    meaning = (row.get("meaning") or "").strip()

                    if not surah_number or not ayah_number or not word or not meaning:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Skipping row {row_number}: missing required values"
                            )
                        )
                        continue

                    ayah_key = (surah_number, ayah_number)
                    sort_order = order_map.get(ayah_key, 0) + 1
                    order_map[ayah_key] = sort_order

                    ayah = Ayah.objects.filter(
                        surah_number=surah_number,
                        ayah_number=ayah_number,
                    ).first()

                    _, created = AyahWordMeaning.objects.update_or_create(
                        surah_number=surah_number,
                        ayah_number=ayah_number,
                        sort_order=sort_order,
                        defaults={
                            "ayah": ayah,
                            "word": word,
                            "word_plain": word_plain,
                            "meaning": meaning,
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except ValueError as exc:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipping row {row_number}: invalid number format ({exc})"
                        )
                    )
                except Exception as exc:
                    self.stdout.write(
                        self.style.WARNING(f"Skipping row {row_number}: {exc}")
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created: {created_count}, Updated: {updated_count}"
            )
        )