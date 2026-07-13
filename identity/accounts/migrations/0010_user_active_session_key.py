# Generated manually for single-device login

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_user_profile_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="active_session_key",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="Current Django session key for single-device login (admins exempt).",
                max_length=40,
            ),
        ),
    ]
