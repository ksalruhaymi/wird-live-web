# Generated manually — clean legacy demo_teacher call/rating data safely.

from django.conf import settings
from django.db import migrations
from django.db.models import Q


def _demo_user_ids(apps):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    TeacherProfile = apps.get_model("tutoring", "TeacherProfile")

    ids = set(
        User.objects.filter(username__iexact="demo_teacher").values_list(
            "id", flat=True
        )
    )
    ids.update(
        User.objects.filter(username__iexact="te").values_list("id", flat=True)
    )
    field_names = {f.name for f in TeacherProfile._meta.local_fields}
    if "is_demo_teacher" in field_names:
        ids.update(
            TeacherProfile.objects.filter(is_demo_teacher=True).values_list(
                "user_id", flat=True
            )
        )
    return sorted(ids)


def cleanup_demo_teacher_legacy(apps, schema_editor):
    """Idempotent cleanup before removing demo_teacher concepts.

    - Detach remaining test-call sessions/recordings from demo users.
    - Delete demo_teacher rating answers/questions/config.
    - Does NOT delete non-test CallSessions or financial rows.
    - Does NOT delete the demo User (handled by remove_demo_teacher command).
    """
    CallSession = apps.get_model("calls", "CallSession")
    CallRecording = apps.get_model("calls", "CallRecording")
    RatingQuestion = apps.get_model("calls", "RatingQuestion")
    RatingCategoryConfig = apps.get_model("calls", "RatingCategoryConfig")
    CallPeerRatingAnswer = apps.get_model("calls", "CallPeerRatingAnswer")

    demo_ids = _demo_user_ids(apps)
    if demo_ids:
        test_qs = CallSession.objects.filter(teacher_id__in=demo_ids).filter(
            Q(is_test_call=True) | Q(service_type="test_call")
        )
        test_ids = list(test_qs.values_list("id", flat=True))
        if test_ids:
            CallSession.objects.filter(id__in=test_ids).update(
                teacher_id=None,
                service_type="test_call",
                is_test_call=True,
            )
            CallRecording.objects.filter(call_session_id__in=test_ids).update(
                teacher_id=None
            )

        CallRecording.objects.filter(
            teacher_id__in=demo_ids,
            call_session__is_test_call=True,
        ).update(teacher_id=None)
        CallRecording.objects.filter(
            teacher_id__in=demo_ids,
            call_session__service_type="test_call",
        ).update(teacher_id=None)

    demo_q = RatingQuestion.objects.filter(category="demo_teacher")
    demo_q_ids = list(demo_q.values_list("id", flat=True))
    if demo_q_ids:
        CallPeerRatingAnswer.objects.filter(question_id__in=demo_q_ids).delete()
        demo_q.delete()
    RatingCategoryConfig.objects.filter(category="demo_teacher").delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0020_detach_test_calls_from_demo_teacher"),
        ("tutoring", "0010_align_tutoring_session_related_names"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(cleanup_demo_teacher_legacy, noop_reverse),
    ]
