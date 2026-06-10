from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("subscription", "0008_decimal_subscription_minutes"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentsubscriptionbalance",
            name="low_minutes_warning_sent_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="تاريخ إرسال تنبيه انخفاض الدقائق",
            ),
        ),
    ]
