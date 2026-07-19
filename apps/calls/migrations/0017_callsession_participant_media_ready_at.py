# Generated manually for participant_media_ready_at

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0016_callsession_is_test_call"),
    ]

    operations = [
        migrations.AddField(
            model_name="callsession",
            name="participant_media_ready_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="جاهزية صوت المشارك (بعد join/publish)",
            ),
        ),
    ]
