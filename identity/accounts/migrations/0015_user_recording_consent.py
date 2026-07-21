from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_rename_demo_account_usernames"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="call_recording_consent_version",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Last accepted real-call recording consent version.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="call_recording_consent_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the user last accepted real-call recording consent.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="test_call_recording_consent_version",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Last accepted test-call recording consent version.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="test_call_recording_consent_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the user last accepted test-call recording consent.",
                null=True,
            ),
        ),
    ]
