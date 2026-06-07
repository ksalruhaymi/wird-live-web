from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calls", "0009_ratingquestion_callpeerratinganswer"),
    ]

    operations = [
        migrations.CreateModel(
            name="RatingCategoryConfig",
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
                    "category",
                    models.CharField(
                        choices=[
                            ("teacher", "تقييم المعلم"),
                            ("student", "تقييم الطالب"),
                            ("demo_teacher", "تقييم المعلم التجريبي"),
                        ],
                        max_length=20,
                        unique=True,
                        verbose_name="نوع التقييم",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(default=True, verbose_name="مفعّل"),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "إعداد نوع التقييم",
                "verbose_name_plural": "إعدادات أنواع التقييم",
            },
        ),
    ]
