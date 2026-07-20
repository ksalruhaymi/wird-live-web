# Generated manually — demo/trial account fields on User.

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_passwordresetcode"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_demo_account",
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text="Protected trial/demo account; excluded from bulk trial cleanup.",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="demo_role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("admin", "مشرف تجريبي"),
                    ("student", "طالب تجريبي"),
                    ("teacher", "معلم تجريبي"),
                ],
                help_text="Demo account kind when is_demo_account=True.",
                max_length=20,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                condition=Q(is_demo_account=True, demo_role__isnull=False),
                fields=("demo_role",),
                name="uniq_demo_account_per_role",
            ),
        ),
    ]
