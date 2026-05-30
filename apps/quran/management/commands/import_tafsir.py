# apps/quran/management/commands/import_tafsir.py

import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.quran.models import TafsirBook, Tafsir


class Command(BaseCommand):
    help = "Import tafsir CSV files into Tafsir model."

    def handle(self, *args, **options):
        # مجلد data داخل تطبيق quran
        data_dir = Path(__file__).resolve().parents[2] / "data"
        if not data_dir.exists():
            raise CommandError(f"Data directory not found: {data_dir}")

        self.stdout.write(self.style.NOTICE(f"Using data directory: {data_dir}"))

        # ربط lang في TafsirBook باسم ملف CSV
        # عدّل الأسماء لو مختلفة عندك
        csv_map = {
            "tafsir_alsa3dy": "tafsir_alsa3dy.csv",
            "tafsir_alqortoby": "tafsir_alqortoby.csv",
            "tafsir_altabary":  "tafsir_altabary.csv",
            "tafsir_albaghawy": "tafsir_albaghawy.csv",
            "tafsir_alkatheer": "tafsir_alkatheer.csv",
            "tafsir_almuyasser": "tafsir_almuyasser.csv",
        }

        for lang, filename in csv_map.items():
            csv_path = data_dir / filename
            if not csv_path.exists():
                self.stdout.write(
                    self.style.WARNING(f"CSV file not found for {lang}: {csv_path}")
                )
                continue

            try:
                book = TafsirBook.objects.get(lang=lang)
            except TafsirBook.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"TafsirBook with lang='{lang}' not found. Skipping.")
                )
                continue

            self.stdout.write(self.style.NOTICE(f"Importing {filename} into {book.name}..."))
            count = self._import_file(book, csv_path)
            self.stdout.write(
                self.style.SUCCESS(f"Imported {count} rows for {book.lang}")
            )

    @transaction.atomic
    def _import_file(self, book: TafsirBook, csv_path: Path) -> int:
        # نحذف القديم لهذا الكتاب قبل إعادة الاستيراد (اختياري لكن مريح)
        Tafsir.objects.filter(book=book).delete()

        created = 0
        entries = []

        with csv_path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            # الأعمدة المتوقعة من الملفات:
            # number,surah_id,no_ayah,"text"
            # (نحن نهمل number)
            if "surah_id" not in reader.fieldnames or \
               not (("no_ayah" in reader.fieldnames) or ("ayah_number" in reader.fieldnames)) or \
               "text" not in reader.fieldnames:
                raise CommandError(
                    f"{csv_path.name} does not contain expected columns "
                    "(surah_id, no_ayah/ayah_number, text)"
                )

            for row in reader:
                try:
                    surah_id = int(row["surah_id"])
                    ayah_number = int(row.get("no_ayah") or row.get("ayah_number"))
                    text = (row.get("text") or "").strip()
                except (ValueError, TypeError):
                    continue

                if not text:
                    continue

                entries.append(
                    Tafsir(
                        book=book,
                        surah_id=surah_id,
                        ayah_number=ayah_number,
                        text=text,
                    )
                )

        Tafsir.objects.bulk_create(entries, batch_size=1000)
        created = len(entries)
        return created