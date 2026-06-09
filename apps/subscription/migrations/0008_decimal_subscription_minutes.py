from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("subscription", "0007_backfill_subscription_balances"),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentsubscriptionbalance",
            name="remaining_minutes",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=12,
                verbose_name="الدقائق المتبقية",
            ),
        ),
        migrations.AlterField(
            model_name="studentsubscriptionbalance",
            name="used_minutes",
            field=models.DecimalField(
                decimal_places=4,
                default=Decimal("0"),
                max_digits=12,
                verbose_name="الدقائق المستخدمة",
            ),
        ),
    ]
