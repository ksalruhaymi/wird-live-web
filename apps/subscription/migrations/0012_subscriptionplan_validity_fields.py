# Generated manually for validity_value / validity_unit on SubscriptionPlan.

from django.db import migrations, models


def forwards_migrate_duration_months(apps, schema_editor):
    SubscriptionPlan = apps.get_model("subscription", "SubscriptionPlan")
    for plan in SubscriptionPlan.objects.all().iterator():
        duration = int(plan.duration_months or 0)
        if duration > 0:
            plan.validity_value = duration
            plan.validity_unit = "months"
        else:
            plan.validity_value = None
            plan.validity_unit = None
        plan.save(update_fields=["validity_value", "validity_unit"])


def backwards_clear_validity(apps, schema_editor):
    SubscriptionPlan = apps.get_model("subscription", "SubscriptionPlan")
    SubscriptionPlan.objects.all().update(validity_value=None, validity_unit=None)


class Migration(migrations.Migration):

    dependencies = [
        ("subscription", "0011_minute_credit_pack"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionplan",
            name="validity_value",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="عدد الأيام أو الأشهر. فارغ مع الوحدة = باقة مفتوحة حتى نفاد الدقائق.",
                null=True,
                verbose_name="قيمة الصلاحية",
            ),
        ),
        migrations.AddField(
            model_name="subscriptionplan",
            name="validity_unit",
            field=models.CharField(
                blank=True,
                choices=[("days", "أيام"), ("months", "أشهر")],
                max_length=10,
                null=True,
                verbose_name="وحدة الصلاحية",
            ),
        ),
        migrations.RunPython(forwards_migrate_duration_months, backwards_clear_validity),
    ]
