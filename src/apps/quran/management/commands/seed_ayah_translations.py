"""
Management command: seed_ayah_translations
Imports ayah_translations.csv into the AyahTranslation table.

Usage: python manage.py seed_ayah_translations
"""
import csv
import os
import time
from collections import defaultdict

from django.core.management.base import BaseCommand

from apps.quran.models import AyahTranslation

DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "ayah_translations.csv",
)

BATCH_SIZE = 2000

EXPECTED_LANGUAGES = {
    "en", "de", "es", "hi", "ur", "fa", "id",
    "fr", "ja", "zh", "nl", "fil", "vi", "as", "si", "so",
}


class Command(BaseCommand):
    help = "Import ayah_translations.csv into AyahTranslation table."

    def handle(self, *args, **options):
        start = time.time()
        self.stdout.write(f"Reading: {DATA_FILE}")

        if not os.path.exists(DATA_FILE):
            self.stderr.write(self.style.ERROR(f"File not found: {DATA_FILE}"))
            return

        # ── Load existing records into a lookup dict: (surah, ayah, lang) → pk
        self.stdout.write("Loading existing records from database…")
        existing = {
            (r.surah_number, r.ayah_number, r.language): r.pk
            for r in AyahTranslation.objects.only(
                "pk", "surah_number", "ayah_number", "language"
            )
        }
        self.stdout.write(f"  Existing records: {len(existing):,}")

        rows_read = 0
        rows_skipped = 0
        langs_seen = set()

        to_create = []
        to_update_objs = []  # list of (pk, new_translation)

        with open(DATA_FILE, encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows_read += 1
                try:
                    surah_num = int(row["surah_number"])
                    ayah_num  = int(row["ayah_number"])
                    lang      = row["language"].strip()
                    text      = row["translation"].strip()
                except (KeyError, ValueError, TypeError):
                    rows_skipped += 1
                    if rows_skipped <= 5:
                        self.stderr.write(
                            self.style.WARNING(f"  Skipping malformed row {rows_read}: {row}")
                        )
                    continue

                if not lang or not text or surah_num < 1 or surah_num > 114 or ayah_num < 1:
                    rows_skipped += 1
                    continue

                langs_seen.add(lang)
                key = (surah_num, ayah_num, lang)

                if key in existing:
                    # Only queue an update if the text actually changed
                    to_update_objs.append((existing[key], text))
                else:
                    to_create.append(
                        AyahTranslation(
                            surah_number=surah_num,
                            ayah_number=ayah_num,
                            language=lang,
                            translation=text,
                        )
                    )

        self.stdout.write(f"  Rows read: {rows_read:,} | Skipped: {rows_skipped:,}")

        # ── Bulk create new records
        created_count = 0
        if to_create:
            for i in range(0, len(to_create), BATCH_SIZE):
                batch = to_create[i : i + BATCH_SIZE]
                AyahTranslation.objects.bulk_create(batch, ignore_conflicts=False)
                created_count += len(batch)
                self.stdout.write(f"  Created batch: {i + len(batch):,} / {len(to_create):,}", ending="\r")
            self.stdout.write("")

        # ── Bulk update existing records
        updated_count = 0
        if to_update_objs:
            pk_to_text = dict(to_update_objs)
            objs_to_update = list(AyahTranslation.objects.filter(pk__in=pk_to_text.keys()))
            for obj in objs_to_update:
                obj.translation = pk_to_text[obj.pk]
            for i in range(0, len(objs_to_update), BATCH_SIZE):
                batch = objs_to_update[i : i + BATCH_SIZE]
                AyahTranslation.objects.bulk_update(batch, ["translation"])
                updated_count += len(batch)

        elapsed = time.time() - start

        # ── Report
        missing_langs = EXPECTED_LANGUAGES - langs_seen
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("━" * 50))
        self.stdout.write(self.style.SUCCESS("Seed complete"))
        self.stdout.write(f"  Records created : {created_count:,}")
        self.stdout.write(f"  Records updated : {updated_count:,}")
        self.stdout.write(f"  Rows skipped    : {rows_skipped:,}")
        self.stdout.write(f"  Languages found : {sorted(langs_seen)}")
        self.stdout.write(f"  Languages count : {len(langs_seen)}")
        if missing_langs:
            self.stdout.write(
                self.style.WARNING(f"  Missing languages: {sorted(missing_langs)}")
            )
        else:
            self.stdout.write(self.style.SUCCESS("  All expected languages present"))
        self.stdout.write(f"  Time elapsed    : {elapsed:.1f}s")
        self.stdout.write(self.style.SUCCESS("━" * 50))
