from django.db import migrations, models


def copy_legacy_app_enabled(apps, schema_editor):
    MobileAppConfig = apps.get_model("mobile", "MobileAppConfig")
    for row in MobileAppConfig.objects.all():
        enabled = bool(row.app_enabled)
        row.android_app_enabled = enabled
        row.ios_app_enabled = enabled
        row.save(update_fields=["android_app_enabled", "ios_app_enabled"])


def noop_reverse(apps, schema_editor):
    # Keep legacy app_enabled as-is; platform fields are dropped on reverse.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("mobile", "0002_mobile_app_versions"),
    ]

    operations = [
        migrations.AddField(
            model_name="mobileappconfig",
            name="android_app_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="mobileappconfig",
            name="ios_app_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(copy_legacy_app_enabled, noop_reverse),
    ]
