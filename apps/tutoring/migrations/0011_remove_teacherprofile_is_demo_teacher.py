# Generated manually — remove TeacherProfile.is_demo_teacher after data cleanup.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tutoring", "0010_align_tutoring_session_related_names"),
        ("calls", "0021_cleanup_demo_teacher_legacy"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="teacherprofile",
            name="is_demo_teacher",
        ),
    ]
