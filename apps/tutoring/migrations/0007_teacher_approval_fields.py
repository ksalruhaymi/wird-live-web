from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def sync_approval_status_from_legacy(apps, schema_editor):
    TeacherProfile = apps.get_model("tutoring", "TeacherProfile")
    for profile in TeacherProfile.objects.all().iterator():
        if profile.is_approved:
            profile.approval_status = "approved"
        elif profile.is_demo_teacher:
            profile.approval_status = "approved"
            profile.is_approved = True
        else:
            profile.approval_status = "pending"
        profile.save(update_fields=["approval_status", "is_approved"])


class Migration(migrations.Migration):

    dependencies = [
        ("tutoring", "0006_teacherprofile_auto_accept_calls_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherprofile",
            name="approval_status",
            field=models.CharField(
                choices=[
                    ("pending", "قيد المراجعة"),
                    ("approved", "مقبول"),
                    ("rejected", "مرفوض"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="rejection_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="teacher_approvals_granted",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teacherprofile",
            name="rejected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="teacher_approvals_rejected",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(
            sync_approval_status_from_legacy,
            migrations.RunPython.noop,
        ),
    ]
