# Generated manually — detach test calls from demo_teacher User safely.

from django.db import migrations


def detach_test_calls_from_demo_teacher(apps, schema_editor):
    """Move historical test calls onto the independent service shape.

    - Sets service_type=test_call and clears teacher_id on test CallSessions.
    - Clears CallRecording.teacher_id for those sessions.
    - Does NOT delete any User (e.g. demo_teacher) to avoid breaking other FKs.
    """
    CallSession = apps.get_model("calls", "CallSession")
    CallRecording = apps.get_model("calls", "CallRecording")

    test_qs = CallSession.objects.filter(is_test_call=True)
    test_ids = list(test_qs.values_list("id", flat=True))

    test_qs.update(service_type="test_call", teacher_id=None)

    if test_ids:
        CallRecording.objects.filter(call_session_id__in=test_ids).update(
            teacher_id=None
        )


def noop_reverse(apps, schema_editor):
    # Irreversible by design: we do not re-attach a synthetic teacher User.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("calls", "0019_test_call_independent_service"),
    ]

    operations = [
        migrations.RunPython(
            detach_test_calls_from_demo_teacher,
            noop_reverse,
        ),
    ]
