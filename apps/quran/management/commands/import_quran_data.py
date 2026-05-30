from pathlib import Path
import csv

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.quran.models import Surah, Ayah
import apps.quran as quran_app


class Command(BaseCommand):
    help = "Import Quran Surahs and Ayahs from CSV files in apps/quran/data/"

    def handle(self, *args, **options):
        # مسار apps/quran/data/
        app_dir = Path(quran_app.__file__).resolve().parent
        data_dir = app_dir / "data"

        if not data_dir.exists():
            raise CommandError(f"Data directory not found: {data_dir}")

        # نبحث عن suwar*.csv و ayat*.csv
        suwar_file = None
        ayat_file = None

        for file in data_dir.glob("*.csv"):
            name = file.name.lower()

            if name.startswith("suwar") and suwar_file is None:
                suwar_file = file
            elif name.startswith("ayat") and ayat_file is None:
                ayat_file = file

        if not suwar_file:
            raise CommandError("No suwar*.csv file found in data directory.")

        self.stdout.write(self.style.WARNING(f"Using data directory: {data_dir}"))
        self.stdout.write(self.style.WARNING(f"Suwar file: {suwar_file.name}"))
        if ayat_file:
            self.stdout.write(self.style.WARNING(f"Ayat file: {ayat_file.name}"))
        else:
            self.stdout.write(self.style.WARNING("No ayat*.csv file found. Ayah import will be skipped."))

        with transaction.atomic():
            self.import_suwar(suwar_file)

            if ayat_file:
                self.import_ayat_from_ayahs_data(ayat_file)

        self.stdout.write(self.style.SUCCESS("Quran data imported successfully."))

    # ---------- السور (من suwar.csv) ----------
    def import_suwar(self, file_path: Path):
        """
        يتوقع suwar.csv بالصيغـة:
        surah_number,surah_name_ar,surah_name_en,page_start,page_end,ayah_count,revelation_type
        """
        self.stdout.write("Importing Suwar...")
        Surah.objects.all().delete()

        suwar = []

        with file_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                suwar.append(
                    Surah(
                        surah_number=int(row["surah_number"]),
                        surah_name_ar=row["surah_name_ar"],
                        surah_name_en=row.get("surah_name_en", "") or "",
                        page_start=int(row["page_start"]),
                        page_end=int(row["page_end"]),
                        ayah_count=int(row["ayah_count"]),
                        revelation_type=row["revelation_type"],  # "meccan" / "medinan"
                    )
                )

        Surah.objects.bulk_create(suwar)
        self.stdout.write(self.style.SUCCESS(f"{len(suwar)} suwar imported."))

    # ---------- الآيات (من ayat*.csv بالهيكل القديم) ----------
    def import_ayat_from_ayahs_data(self, file_path: Path):
        """
        يتوقع ayat*.csv بالصيغـة القديمة:
        no_ayah_in_quran,page_id,surah_id,no_ayah_in_surah,ayah_formation,ayah_without

        ونحوّلها لموديل Ayah:
        surah_number, ayah_number, page_number, juz_number, text
        """
        self.stdout.write("Importing Ayat from ayat-data...")
        Ayah.objects.all().delete()

        batch = []
        batch_size = 2000
        total = 0

        with file_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                surah_number = int(row["surah_id"])
                ayah_number = int(row["no_ayah_in_surah"])
                page_number = int(row["page_id"])
                text = row.get("ayah_formation", "") or ""

                # مؤقتًا: نجعل الجزء 1 (تقدر تربطه لاحقًا من ملف الأجزاء)
                juz_number = 1

                batch.append(
                    Ayah(
                        surah_number=surah_number,
                        ayah_number=ayah_number,
                        page_number=page_number,
                        juz_number=juz_number,
                        text=text,
                    )
                )
                total += 1

                if len(batch) >= batch_size:
                    Ayah.objects.bulk_create(batch)
                    batch.clear()

        if batch:
            Ayah.objects.bulk_create(batch)

        self.stdout.write(self.style.SUCCESS(f"{total} ayat imported."))