from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0012_callsession_minutes_charged"),
    ]

    operations = [
        migrations.AlterField(
            model_name="callsession",
            name="minutes_charged",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=12,
                null=True,
                verbose_name="دقائق مخصومة من الرصيد",
            ),
        ),
    ]
