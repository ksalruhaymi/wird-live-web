# Generated manually — drop demo_teacher rating category choices.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0021_cleanup_demo_teacher_legacy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ratingquestion",
            name="category",
            field=models.CharField(
                choices=[
                    ("teacher", "تقييم المعلم"),
                    ("student", "تقييم الطالب"),
                ],
                max_length=20,
                verbose_name="نوع التقييم",
            ),
        ),
        migrations.AlterField(
            model_name="ratingcategoryconfig",
            name="category",
            field=models.CharField(
                choices=[
                    ("teacher", "تقييم المعلم"),
                    ("student", "تقييم الطالب"),
                ],
                max_length=20,
                unique=True,
                verbose_name="نوع التقييم",
            ),
        ),
    ]
