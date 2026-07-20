# Generated manually — rename legacy demo usernames safely.

from django.db import migrations
from django.db.models import Q


RENAMES = (
    # (legacy_usernames, new_username, demo_role, full_name)
    (("demo_supervisor",), "super", "admin", "مشرف - اختبار"),
    (("demo_student",), "student", "student", "طالب - اختبار"),
    (("demo_teacher",), "teacher", "teacher", "معلم - اختبار"),
)


def _find_user(User, *, demo_role: str, new_username: str, legacy_usernames: tuple[str, ...]):
    user = (
        User.objects.filter(is_demo_account=True, demo_role=demo_role)
        .order_by("id")
        .first()
    )
    if user is not None:
        return user

    q = Q(username__iexact=new_username)
    for legacy in legacy_usernames:
        q |= Q(username__iexact=legacy)
    return User.objects.filter(q).order_by("id").first()


def rename_demo_usernames(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    StudentProfile = apps.get_model("tutoring", "StudentProfile")
    TeacherProfile = apps.get_model("tutoring", "TeacherProfile")

    for legacy_usernames, new_username, demo_role, full_name in RENAMES:
        user = _find_user(
            User,
            demo_role=demo_role,
            new_username=new_username,
            legacy_usernames=legacy_usernames,
        )
        if user is None:
            continue

        if user.username != new_username:
            conflict = (
                User.objects.filter(username__iexact=new_username)
                .exclude(pk=user.pk)
                .exists()
            )
            if conflict:
                raise RuntimeError(
                    f"Cannot rename demo account id={user.pk} "
                    f"({user.username!r} → {new_username!r}): "
                    f"username {new_username!r} already exists. "
                    f"Resolve the conflict manually, then re-run migrate."
                )
            user.username = new_username

        user.full_name = full_name
        user.is_demo_account = True
        user.demo_role = demo_role
        user.save(
            update_fields=["username", "full_name", "is_demo_account", "demo_role"]
        )

        if demo_role == "student":
            StudentProfile.objects.filter(user_id=user.id).update(
                display_name=full_name
            )
        elif demo_role == "teacher":
            TeacherProfile.objects.filter(user_id=user.id).update(
                display_name=full_name
            )


def noop_reverse(apps, schema_editor):
    # Irreversible: we do not force-rename back to legacy usernames.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_alter_user_options"),
        ("tutoring", "0011_remove_teacherprofile_is_demo_teacher"),
    ]

    operations = [
        migrations.RunPython(rename_demo_usernames, noop_reverse),
    ]
