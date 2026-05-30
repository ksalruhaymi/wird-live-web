from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_remove_user_department_alter_user_gender"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="systemauthsettings",
            name="allow_api_login",
        ),
    ]
