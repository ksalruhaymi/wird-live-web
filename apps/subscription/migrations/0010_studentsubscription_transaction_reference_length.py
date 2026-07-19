from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscription", "0009_balance_low_minutes_warning_sent_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="studentsubscription",
            name="transaction_reference",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]
