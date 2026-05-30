# Generated manually for audio listen analytics

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("quran", "0008_khatmaprogress_delete_dailyreading"),
    ]

    operations = [
        migrations.CreateModel(
            name="AudioListenEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_key", models.CharField(blank=True, db_index=True, max_length=80)),
                ("mushaf_key", models.CharField(blank=True, db_index=True, max_length=40)),
                ("qari_code", models.CharField(blank=True, db_index=True, max_length=120)),
                ("surah_number", models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
                ("ayah_number", models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
                ("page_number", models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
                ("event_type", models.CharField(choices=[("play", "Play"), ("pause", "Pause"), ("ended", "Ended"), ("progress_50", "Progress 50%")], db_index=True, max_length=30)),
                ("current_time", models.FloatField(default=0)),
                ("duration", models.FloatField(default=0)),
                ("percent", models.PositiveSmallIntegerField(db_index=True, default=0)),
                ("audio_src", models.TextField(blank=True)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("country", models.CharField(blank=True, db_index=True, max_length=2)),
                ("user_agent", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="audio_listen_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["created_at", "event_type"], name="quran_audio_created_9d07a0_idx"),
                    models.Index(fields=["qari_code", "event_type"], name="quran_audio_qari_co_9f8f0c_idx"),
                    models.Index(fields=["mushaf_key", "page_number"], name="quran_audio_mushaf__07a71d_idx"),
                    models.Index(fields=["surah_number", "ayah_number"], name="quran_audio_surah_n_6a4f77_idx"),
                ],
            },
        ),
    ]
