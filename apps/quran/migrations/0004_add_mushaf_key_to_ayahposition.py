from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quran", "0003_alter_qurra_options_remove_qurra_fullname_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="ayahposition",
            name="mushaf_key",
            field=models.CharField(
                db_index=True,
                default="hafs",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="ayahposition",
            index=models.Index(
                fields=["mushaf_key", "page_number"],
                name="quran_ayahp_mushaf__a7dc2f_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="ayahposition",
            index=models.Index(
                fields=["mushaf_key", "surah_number", "ayah_number"],
                name="quran_ayahp_mushaf__2c8eab_idx",
            ),
        ),
    ]