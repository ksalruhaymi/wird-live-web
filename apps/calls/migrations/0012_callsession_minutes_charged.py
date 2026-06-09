from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0011_callsession_is_interview_call"),
    ]

    operations = [
        migrations.AddField(
            model_name="callsession",
            name="minutes_charged",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="دقائق مخصومة من الرصيد",
            ),
        ),
    ]
