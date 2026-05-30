from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("hifz", "0003_recitationattempt"),
    ]

    operations = [
        migrations.CreateModel(
            name="ThematicTopic",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_id", models.PositiveSmallIntegerField(db_index=True, unique=True)),
                ("color_id", models.PositiveSmallIntegerField(db_index=True)),
                ("color_name_ar", models.CharField(max_length=50)),
                ("color_hex", models.CharField(max_length=20)),
                ("topic_id", models.PositiveSmallIntegerField(db_index=True, unique=True)),
                ("topic_ar", models.CharField(max_length=255)),
            ],
            options={
                "verbose_name": "Thematic Topic",
                "verbose_name_plural": "Thematic Topics",
                "ordering": ["color_id", "topic_id"],
            },
        ),
        migrations.CreateModel(
            name="AyahThematicClassification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("surah_number", models.PositiveSmallIntegerField(db_index=True)),
                ("ayah_from", models.PositiveSmallIntegerField(db_index=True)),
                ("ayah_to", models.PositiveSmallIntegerField(db_index=True)),
                ("topic_text", models.CharField(blank=True, max_length=255)),
                ("notes", models.TextField(blank=True)),
                ("topic", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ayah_classifications", to="hifz.thematictopic")),
            ],
            options={
                "verbose_name": "Ayah Thematic Classification",
                "verbose_name_plural": "Ayah Thematic Classifications",
                "ordering": ["surah_number", "ayah_from", "ayah_to", "topic__topic_id"],
            },
        ),
        migrations.AddIndex(
            model_name="thematictopic",
            index=models.Index(fields=["color_id", "topic_id"], name="hifz_themat_color_i_1c8158_idx"),
        ),
        migrations.AddIndex(
            model_name="thematictopic",
            index=models.Index(fields=["topic_id"], name="hifz_themat_topic_i_0f0987_idx"),
        ),
        migrations.AddIndex(
            model_name="ayahthematicclassification",
            index=models.Index(fields=["surah_number", "ayah_from", "ayah_to"], name="hifz_ayaht_surah_n_6db53d_idx"),
        ),
        migrations.AddIndex(
            model_name="ayahthematicclassification",
            index=models.Index(fields=["surah_number", "ayah_from"], name="hifz_ayaht_surah_n_b79c60_idx"),
        ),
        migrations.AddIndex(
            model_name="ayahthematicclassification",
            index=models.Index(fields=["topic", "surah_number"], name="hifz_ayaht_topic_i_8fbc4a_idx"),
        ),
        migrations.AddConstraint(
            model_name="ayahthematicclassification",
            constraint=models.UniqueConstraint(fields=("surah_number", "ayah_from", "ayah_to", "topic"), name="unique_hifz_ayah_thematic_range"),
        ),
        migrations.AddConstraint(
            model_name="ayahthematicclassification",
            constraint=models.CheckConstraint(condition=models.Q(("ayah_to__gte", models.F("ayah_from"))), name="hifz_ayah_thematic_valid_range"),
        ),
    ]
