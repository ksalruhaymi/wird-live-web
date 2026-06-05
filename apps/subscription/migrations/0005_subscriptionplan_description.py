from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("subscription", "0004_subscriptionplan_minutes"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="description",
            field=models.TextField(
                blank=True,
                default="",
                verbose_name="وصف الباقة",
            ),
        ),
    ]
