from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quran", "0011_ayahtranslation"),
    ]

    operations = [
        migrations.AddField(
            model_name="qurra",
            name="is_visible",
            field=models.BooleanField(default=True),
        ),
    ]
