from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("subscription", "0005_subscriptionplan_description"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="studentsubscription",
            name="expiry_after",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="تاريخ الانتهاء بعد العملية",
            ),
        ),
        migrations.AddField(
            model_name="studentsubscription",
            name="expiry_before",
            field=models.DateField(
                blank=True,
                null=True,
                verbose_name="تاريخ الانتهاء قبل العملية",
            ),
        ),
        migrations.AddField(
            model_name="studentsubscription",
            name="minutes_after",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="الدقائق بعد العملية",
            ),
        ),
        migrations.AddField(
            model_name="studentsubscription",
            name="minutes_before",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="الدقائق قبل العملية",
            ),
        ),
        migrations.AddField(
            model_name="studentsubscription",
            name="plan_minutes_added",
            field=models.PositiveIntegerField(
                default=0,
                verbose_name="دقائق مضافة",
            ),
        ),
        migrations.AddField(
            model_name="studentsubscription",
            name="transaction_type",
            field=models.CharField(
                blank=True,
                default="purchase",
                max_length=32,
                verbose_name="نوع العملية",
            ),
        ),
        migrations.CreateModel(
            name="StudentSubscriptionBalance",
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
                (
                    "current_plan_title",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=255,
                        verbose_name="الباقة الحالية",
                    ),
                ),
                (
                    "remaining_minutes",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="الدقائق المتبقية",
                    ),
                ),
                (
                    "used_minutes",
                    models.PositiveIntegerField(
                        default=0,
                        verbose_name="الدقائق المستخدمة",
                    ),
                ),
                (
                    "expires_at",
                    models.DateField(
                        blank=True,
                        null=True,
                        verbose_name="تاريخ الانتهاء",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "نشط"),
                            ("expired", "منتهي"),
                            ("cancelled", "ملغي"),
                        ],
                        default="expired",
                        max_length=20,
                        verbose_name="الحالة",
                    ),
                ),
                (
                    "last_purchase_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        verbose_name="آخر عملية شراء",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subscription_balance",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المستخدم",
                    ),
                ),
            ],
            options={
                "verbose_name": "رصيد اشتراك طالب",
                "verbose_name_plural": "أرصدة اشتراك الطلاب",
            },
        ),
    ]
