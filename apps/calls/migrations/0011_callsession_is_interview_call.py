from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0010_ratingcategoryconfig"),
    ]

    operations = [
        migrations.AddField(
            model_name="callsession",
            name="is_interview_call",
            field=models.BooleanField(
                default=False,
                verbose_name="مقابلة إدارة (مكالمة معلم جديد)",
            ),
        ),
    ]

