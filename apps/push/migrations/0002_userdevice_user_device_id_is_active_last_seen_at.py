import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("push", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="userdevice",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="devices",
                to=settings.AUTH_USER_MODEL,
                verbose_name="المستخدم",
            ),
        ),
        migrations.AddField(
            model_name="userdevice",
            name="device_id",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="معرّف الجهاز",
            ),
        ),
        migrations.AddField(
            model_name="userdevice",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="نشط"),
        ),
        migrations.AddField(
            model_name="userdevice",
            name="last_seen_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="آخر ظهور"),
        ),
        migrations.AlterField(
            model_name="userdevice",
            name="fcm_token",
            field=models.TextField(unique=True, verbose_name="FCM Token"),
        ),
        migrations.AlterField(
            model_name="userdevice",
            name="platform",
            field=models.CharField(
                choices=[("android", "Android"), ("ios", "iOS")],
                max_length=10,
                verbose_name="المنصة",
            ),
        ),
        migrations.AddIndex(
            model_name="userdevice",
            index=models.Index(
                fields=["user", "is_active"],
                name="push_dev_user_active_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="userdevice",
            index=models.Index(
                fields=["user", "device_id"],
                name="push_dev_user_devid_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="userdevice",
            index=models.Index(
                fields=["is_active", "last_seen_at"],
                name="push_dev_active_seen_idx",
            ),
        ),
    ]
