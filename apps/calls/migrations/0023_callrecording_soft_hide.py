# Generated manually for soft-hide per participant.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0022_remove_demo_teacher_rating_category"),
    ]

    operations = [
        migrations.AddField(
            model_name="callrecording",
            name="hidden_by_student_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="callrecording",
            name="hidden_by_teacher_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
