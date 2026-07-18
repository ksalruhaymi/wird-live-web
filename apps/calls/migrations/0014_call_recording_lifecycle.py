# Generated manually for call/recording lifecycle hardening.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0013_decimal_minutes_charged"),
    ]

    operations = [
        migrations.AddField(
            model_name="callsession",
            name="end_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callsession",
            name="end_reason",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="callsession",
            name="end_error",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="callsession",
            name="last_heartbeat_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callsession",
            name="finalized_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="callsession",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "بانتظار المعلم"),
                    ("active", "نشط"),
                    ("ending", "جاري الإنهاء"),
                    ("ended", "منتهي"),
                    ("rejected", "مرفوض"),
                    ("missed", "لم يتم الرد"),
                    ("cancelled", "ملغي"),
                    ("failed", "فشل"),
                ],
                default="pending",
                max_length=20,
                verbose_name="الحالة",
            ),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="stop_requested_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="stopped_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="processing_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="ready_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="failed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="finalized_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="failure_code",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="last_query_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="query_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="stop_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="next_retry_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="callrecording",
            name="recording_status",
            field=models.CharField(
                choices=[
                    ("idle", "Idle"),
                    ("starting", "Starting"),
                    ("recording", "Recording"),
                    ("stop_requested", "Stop requested"),
                    ("stopping", "Stopping"),
                    ("processing", "Processing"),
                    ("completed", "Completed"),
                    ("no_media", "No media"),
                    ("failed", "Failed"),
                    ("expired", "Expired"),
                    ("skipped", "Skipped"),
                    ("cancelled", "Cancelled"),
                ],
                default="idle",
                max_length=20,
            ),
        ),
    ]
