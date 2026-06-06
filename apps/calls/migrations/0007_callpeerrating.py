from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("calls", "0006_callrecording_recording_object_key"),
    ]

    operations = [
        migrations.CreateModel(
            name="CallPeerRating",
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
                    "rater_role",
                    models.CharField(
                        choices=[("student", "طالب"), ("teacher", "معلّم")],
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "بانتظار التقييم"),
                            ("completed", "تم التقييم"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("competence", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("clarity", models.PositiveSmallIntegerField(blank=True, null=True)),
                (
                    "audio_quality",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "call_session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="peer_ratings",
                        to="calls.callsession",
                    ),
                ),
                (
                    "rated",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="call_ratings_received",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "rater",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="call_ratings_given",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "تقييم طرف المكالمة",
                "verbose_name_plural": "تقييمات أطراف المكالمات",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="callpeerrating",
            constraint=models.UniqueConstraint(
                fields=("call_session", "rater"),
                name="calls_callpeerrating_unique_call_rater",
            ),
        ),
    ]
