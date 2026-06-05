from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("subscription", "0003_studentsubscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="minutes",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="دقائق الباقة",
            ),
        ),
    ]
