"""
Data migration: populate Ayah.juz_number from exact page-based boundaries.
Boundaries match ayahs.csv (Hafs 604-page Mushaf).
"""
from django.db import migrations

# (juz_number, start_page, end_page)
JUZ_RANGES = [
    (1, 1, 21), (2, 22, 41), (3, 42, 61), (4, 62, 81), (5, 82, 101),
    (6, 102, 121), (7, 122, 141), (8, 142, 161), (9, 162, 181), (10, 182, 201),
    (11, 202, 221), (12, 222, 241), (13, 242, 261), (14, 262, 281), (15, 282, 301),
    (16, 302, 321), (17, 322, 341), (18, 342, 361), (19, 362, 381), (20, 382, 401),
    (21, 402, 421), (22, 422, 441), (23, 442, 461), (24, 462, 481), (25, 482, 501),
    (26, 502, 521), (27, 522, 541), (28, 542, 561), (29, 562, 581), (30, 582, 604),
]


def fix_juz_numbers(apps, schema_editor):
    Ayah = apps.get_model("quran", "Ayah")
    for juz_num, start_page, end_page in JUZ_RANGES:
        Ayah.objects.filter(
            page_number__gte=start_page,
            page_number__lte=end_page,
        ).update(juz_number=juz_num)


def reverse_juz_numbers(apps, schema_editor):
    # Reset to 1 (prior state before this migration)
    Ayah = apps.get_model("quran", "Ayah")
    Ayah.objects.all().update(juz_number=1)


class Migration(migrations.Migration):
    dependencies = [
        ("quran", "0013_khatma_tracking_mode_and_wird_status"),
    ]

    operations = [
        migrations.RunPython(fix_juz_numbers, reverse_code=reverse_juz_numbers),
    ]
