# Generated manually for dual-party media-ready timestamps

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0017_callsession_participant_media_ready_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="callsession",
            name="student_media_ready_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="جاهزية صوت الطالب (بعد join/publish)",
            ),
        ),
        migrations.AddField(
            model_name="callsession",
            name="teacher_media_ready_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="جاهزية صوت المعلم (بعد join/publish)",
            ),
        ),
    ]
