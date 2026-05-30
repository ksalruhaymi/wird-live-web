# import_hifz_thematic_data.py

import csv
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.hifz.models import AyahThematicClassification, ThematicTopic


class Command(BaseCommand):
    help = "Import hifz thematic topics and ayah classifications from CSV files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--topics-csv",
            type=str,
            default="apps/quran/data/thematic_coloring.csv",
            help="Path to thematic_coloring.csv",
        )
        parser.add_argument(
            "--classifications-csv",
            type=str,
            default="apps/quran/data/ayah_classification.csv",
            help="Path to ayah_classification.csv",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete old thematic records before importing",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        topics_path = Path(options["topics_csv"])
        classifications_path = Path(options["classifications_csv"])

        if not topics_path.exists():
            self.stderr.write(self.style.ERROR(f"CSV file not found: {topics_path}"))
            return

        if not classifications_path.exists():
            self.stderr.write(self.style.ERROR(f"CSV file not found: {classifications_path}"))
            return

        if options["clear"]:
            self.stdout.write("Deleting old hifz thematic records...")
            AyahThematicClassification.objects.all().delete()
            ThematicTopic.objects.all().delete()

        created_topics, updated_topics = self.import_topics(topics_path)
        created_classifications, updated_classifications = self.import_classifications(classifications_path)

        self.stdout.write(
            self.style.SUCCESS(
                "Done. "
                f"Topics created: {created_topics}, Topics updated: {updated_topics}, "
                f"Classifications created: {created_classifications}, "
                f"Classifications updated: {updated_classifications}"
            )
        )

    def import_topics(self, path):
        required_columns = {
            "id",
            "color_id",
            "color_name_ar",
            "color_hex",
            "topic_id",
            "topic_ar",
        }
        created_count = 0
        updated_count = 0

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            self.validate_headers(reader, required_columns, path)

            for row_number, row in enumerate(reader, start=2):
                try:
                    source_id = self.to_int(row.get("id"), "id", row_number)
                    color_id = self.to_int(row.get("color_id"), "color_id", row_number)
                    topic_id = self.to_int(row.get("topic_id"), "topic_id", row_number)
                    color_name_ar = self.clean(row.get("color_name_ar"))
                    color_hex = self.clean(row.get("color_hex"))
                    topic_ar = self.clean(row.get("topic_ar"))

                    if not color_name_ar or not color_hex or not topic_ar:
                        self.stdout.write(
                            self.style.WARNING(f"Skipping topic row {row_number}: missing text values")
                        )
                        continue

                    _, created = ThematicTopic.objects.update_or_create(
                        topic_id=topic_id,
                        defaults={
                            "source_id": source_id,
                            "color_id": color_id,
                            "color_name_ar": color_name_ar,
                            "color_hex": color_hex,
                            "topic_ar": topic_ar,
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as exc:
                    self.stdout.write(
                        self.style.WARNING(f"Skipping topic row {row_number}: {exc}")
                    )

        return created_count, updated_count

    def import_classifications(self, path):
        required_columns = {
            "surah_number",
            "ayah_from",
            "ayah_to",
            "topic_id",
            "topic",
            "notes",
        }
        created_count = 0
        updated_count = 0

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            self.validate_headers(reader, required_columns, path)

            for row_number, row in enumerate(reader, start=2):
                try:
                    surah_number = self.to_int(row.get("surah_number"), "surah_number", row_number)
                    ayah_from = self.to_int(row.get("ayah_from"), "ayah_from", row_number)
                    ayah_to = self.to_int(row.get("ayah_to"), "ayah_to", row_number)
                    topic_id = self.to_int(row.get("topic_id"), "topic_id", row_number)
                    topic_text = self.clean(row.get("topic"))
                    notes = self.clean(row.get("notes"))

                    if ayah_to < ayah_from:
                        self.stdout.write(
                            self.style.WARNING(f"Skipping classification row {row_number}: invalid ayah range")
                        )
                        continue

                    topic = ThematicTopic.objects.filter(topic_id=topic_id).first()
                    if not topic:
                        self.stdout.write(
                            self.style.WARNING(f"Skipping classification row {row_number}: topic_id {topic_id} not found")
                        )
                        continue

                    _, created = AyahThematicClassification.objects.update_or_create(
                        surah_number=surah_number,
                        ayah_from=ayah_from,
                        ayah_to=ayah_to,
                        topic=topic,
                        defaults={
                            "topic_text": topic_text,
                            "notes": notes,
                        },
                    )

                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                except Exception as exc:
                    self.stdout.write(
                        self.style.WARNING(f"Skipping classification row {row_number}: {exc}")
                    )

        return created_count, updated_count

    def validate_headers(self, reader, required_columns, path):
        if not reader.fieldnames:
            raise ValueError(f"CSV file has no headers: {path}")

        missing_columns = required_columns - set(reader.fieldnames)
        if missing_columns:
            raise ValueError(
                f"Missing required columns in {path}: {', '.join(sorted(missing_columns))}"
            )

    def clean(self, value):
        return (value or "").strip()

    def to_int(self, value, field_name, row_number):
        value = self.clean(value)
        if not value:
            raise ValueError(f"missing {field_name}")
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"invalid {field_name} at row {row_number}: {value}") from exc
