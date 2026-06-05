import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notification", "0002_notification_channel"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AppNotification",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("is_active", models.BooleanField(default=True)),
                (
                    "target_type",
                    models.CharField(
                        choices=[("all", "جميع المستخدمين")],
                        default="all",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="app_notifications_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "تنبيه التطبيق",
                "verbose_name_plural": "تنبيهات التطبيق",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="AppNotificationRead",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("read_at", models.DateTimeField(auto_now_add=True)),
                (
                    "notification",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reads",
                        to="notification.appnotification",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="app_notification_reads",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "قراءة تنبيه التطبيق",
                "verbose_name_plural": "قراءات تنبيهات التطبيق",
            },
        ),
        migrations.AddConstraint(
            model_name="appnotificationread",
            constraint=models.UniqueConstraint(
                fields=("user", "notification"),
                name="uniq_app_notification_read_user_notification",
            ),
        ),
    ]
