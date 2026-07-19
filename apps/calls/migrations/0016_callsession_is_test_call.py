# Generated manually for is_test_call on CallSession

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0015_call_recording_consent"),
    ]

    operations = [
        migrations.AddField(
            model_name="callsession",
            name="is_test_call",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="اتصال تجريبي (اختبار جودة)",
            ),
        ),
    ]
