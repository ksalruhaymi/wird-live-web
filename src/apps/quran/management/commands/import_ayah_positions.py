import csv
import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand
from apps.quran.models import AyahPosition


class Command(BaseCommand):
    help = "Import ayah positions from CSV with polygon and mushaf_key safely"

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            type=str,
            default="apps/quran/data/ayahposition.csv",
            help="Path to the ayah positions CSV file",
        )
        parser.add_argument(
            "--mushaf",
            type=str,
            default=None,
            help="Optional: import only this mushaf key",
        )
        parser.add_argument(
            "--delete-old",
            action="store_true",
            help="Delete old records before import",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv"])
        only_mushaf = options["mushaf"]
        delete_old = options["delete_old"]

        if not csv_path.exists():
            self.stderr.write(self.style.ERROR(f"CSV file not found: {csv_path}"))
            return

        objects = []
        mushaf_keys_found = set()
        skipped = 0

        def to_int(value, default=None):
            value = str(value or "").strip().lower()

            if value in {"", "null", "none"}:
                return default

            try:
                return int(value)
            except ValueError:
                return default

        def to_float(value):
            value = str(value or "").strip().lower()

            if value in {"", "null", "none"}:
                return 0.0

            try:
                return float(value)
            except ValueError:
                return 0.0

        def clean_value(value):
            return str(value or "").strip().strip('"').strip("'").strip()

        def parse_polygon(raw_polygon, x, y, width, height):
            polygon_str = str(raw_polygon or "").strip()

            if polygon_str.startswith('"') and polygon_str.endswith('"'):
                polygon_str = polygon_str[1:-1]

            if polygon_str:
                try:
                    return json.loads(polygon_str)
                except Exception:
                    pass

                try:
                    fixed = polygon_str

                    fixed = fixed.replace('""', '"')
                    fixed = fixed.replace("{'", "{")
                    fixed = fixed.replace("'}", "}")
                    fixed = fixed.replace(",'", ",")
                    fixed = fixed.replace("'[", "[")
                    fixed = fixed.replace("]'", "]")

                    fixed = re.sub(
                        r"""['"]+\s*([a-zA-Z_]+)\s*['"]+\s*:""",
                        r'"\1":',
                        fixed,
                    )

                    return json.loads(fixed)
                except Exception:
                    pass

            return [
                {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                }
            ]

        with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            file.readline()

            for line_number, line in enumerate(file, start=2):
                line = line.strip()

                if not line:
                    continue

                parts = line.split(",")

                if len(parts) < 11:
                    skipped += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"Skipped line {line_number}: invalid column count"
                        )
                    )
                    continue

                row_id = clean_value(parts[0])
                surah_number = to_int(parts[1])
                ayah_number = to_int(parts[2])
                page_number = to_int(parts[3])

                x = to_float(parts[4])
                y = to_float(parts[5])
                width = to_float(parts[6])
                height = to_float(parts[7])

                polygon_raw = ",".join(parts[8:-2]).strip()
                ayah_id = clean_value(parts[-2])
                mushaf_key = clean_value(parts[-1])

                if not mushaf_key:
                    skipped += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"Skipped line {line_number}: empty mushaf_key"
                        )
                    )
                    continue

                if only_mushaf and mushaf_key != only_mushaf:
                    continue

                if not surah_number or not page_number:
                    skipped += 1
                    self.stderr.write(
                        self.style.WARNING(
                            f"Skipped line {line_number}: invalid surah or page"
                        )
                    )
                    continue

                polygon_value = parse_polygon(
                    polygon_raw,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                )

                mushaf_keys_found.add(mushaf_key)

                objects.append(
                    AyahPosition(
                        mushaf_key=mushaf_key,
                        surah_number=surah_number,
                        ayah_number=ayah_number,
                        page_number=page_number,
                        x=x,
                        y=y,
                        width=width,
                        height=height,
                        polygon=polygon_value,
                        ayah_id=to_int(ayah_id),
                    )
                )

        if delete_old:
            if only_mushaf:
                self.stdout.write(f"Deleting old records for mushaf: {only_mushaf}")
                AyahPosition.objects.filter(mushaf_key=only_mushaf).delete()
            else:
                self.stdout.write(
                    f"Deleting old records for mushafs: {', '.join(sorted(mushaf_keys_found))}"
                )
                AyahPosition.objects.filter(mushaf_key__in=mushaf_keys_found).delete()

        AyahPosition.objects.bulk_create(objects, batch_size=1000)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(objects)} records successfully. Skipped: {skipped}"
            )
        )