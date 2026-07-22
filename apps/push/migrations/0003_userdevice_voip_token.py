from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("push", "0002_userdevice_user_device_id_is_active_last_seen_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="userdevice",
            name="voip_token",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                max_length=255,
                verbose_name="VoIP Token (iOS PushKit)",
            ),
        ),
    ]
