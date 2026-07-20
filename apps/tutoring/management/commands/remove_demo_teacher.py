"""Safely inspect and delete legacy demo_teacher accounts.

Usage:
  python manage.py remove_demo_teacher --check
  python manage.py remove_demo_teacher --execute
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.models import Q

from apps.calls.models import CallRecording, CallSession, RatingQuestion
from apps.tutoring.models import TeacherAvailability, TeacherProfile

User = get_user_model()

DEMO_USERNAMES = ("demo_teacher", "te")


def _demo_users():
    qs = User.objects.filter(
        Q(username__iexact="demo_teacher") | Q(username__iexact="te")
    )
    # Legacy profiles may still exist mid-migration; field may be gone.
    profile_ids = []
    if any(f.name == "is_demo_teacher" for f in TeacherProfile._meta.get_fields()):
        profile_ids = list(
            TeacherProfile.objects.filter(is_demo_teacher=True).values_list(
                "user_id", flat=True
            )
        )
    if profile_ids:
        qs = User.objects.filter(Q(id__in=qs) | Q(id__in=profile_ids))
    return list(qs.distinct().order_by("id"))


def _fk_refs_to_users(user_ids: list[int]) -> list[tuple[str, str, int]]:
    if not user_ids:
        return []
    refs = []
    with connection.cursor() as c:
        c.execute(
            """
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND ccu.table_name = %s
            """,
            [User._meta.db_table],
        )
        fks = c.fetchall()
        for table, col in fks:
            try:
                c.execute(
                    f'SELECT COUNT(*) FROM "{table}" WHERE "{col}" = ANY(%s)',
                    [user_ids],
                )
                n = c.fetchone()[0]
                if n:
                    refs.append((table, col, n))
            except Exception:
                connection.rollback()
    return refs


def _table_columns(table: str) -> set[str]:
    with connection.cursor() as c:
        c.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s
            """,
            [table],
        )
        return {r[0] for r in c.fetchall()}


def collect_report(users) -> dict:
    ids = [u.id for u in users]
    sess_cols = _table_columns(CallSession._meta.db_table)
    sessions_total = 0
    sessions_test = 0
    sessions_non_test = 0
    non_test_ids: list[int] = []
    schema_note = ""

    if ids:
        with connection.cursor() as c:
            c.execute(
                f'SELECT COUNT(*) FROM "{CallSession._meta.db_table}" '
                f'WHERE teacher_id = ANY(%s)',
                [ids],
            )
            sessions_total = c.fetchone()[0]

            if "is_test_call" in sess_cols and "service_type" in sess_cols:
                c.execute(
                    f'SELECT id, is_test_call, service_type FROM "{CallSession._meta.db_table}" '
                    f'WHERE teacher_id = ANY(%s)',
                    [ids],
                )
                rows = c.fetchall()
                for sid, is_test, service_type in rows:
                    if is_test or service_type == "test_call":
                        sessions_test += 1
                    else:
                        sessions_non_test += 1
                        if len(non_test_ids) < 50:
                            non_test_ids.append(sid)
            else:
                sessions_non_test = sessions_total
                schema_note = (
                    "CallSession missing is_test_call/service_type — "
                    "apply calls migrations before --execute. "
                    "Treating all linked sessions as non-test blockers."
                )
                c.execute(
                    f'SELECT id FROM "{CallSession._meta.db_table}" '
                    f'WHERE teacher_id = ANY(%s) LIMIT 50',
                    [ids],
                )
                non_test_ids = [r[0] for r in c.fetchall()]

    recordings = 0
    if ids:
        recordings = CallRecording.objects.filter(teacher_id__in=ids).count()

    financial = {}
    try:
        from apps.subscription.models import StudentSubscription, StudentSubscriptionBalance

        financial["subscriptions"] = (
            StudentSubscription.objects.filter(user_id__in=ids).count() if ids else 0
        )
        financial["balances"] = (
            StudentSubscriptionBalance.objects.filter(user_id__in=ids).count()
            if ids
            else 0
        )
    except Exception:
        financial["subscriptions"] = "n/a"
        financial["balances"] = "n/a"

    return {
        "users": users,
        "user_ids": ids,
        "profiles": TeacherProfile.objects.filter(user_id__in=ids).count() if ids else 0,
        "availability": (
            TeacherAvailability.objects.filter(teacher_id__in=ids).count() if ids else 0
        ),
        "sessions_total": sessions_total,
        "sessions_test": sessions_test,
        "sessions_non_test": sessions_non_test,
        "non_test_session_ids": non_test_ids,
        "recordings": recordings,
        "rating_questions_demo": RatingQuestion.objects.filter(
            category="demo_teacher"
        ).count(),
        "financial": financial,
        "fk_refs": _fk_refs_to_users(ids),
        "schema_note": schema_note,
    }


class Command(BaseCommand):
    help = (
        "Inspect or delete legacy demo_teacher users after migrations. "
        "Use --check first; --execute refuses if non-test sessions or "
        "financial rows remain."
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--check",
            action="store_true",
            help="Report all demo_teacher references without modifying data.",
        )
        group.add_argument(
            "--execute",
            action="store_true",
            help="Delete demo_teacher users after safety checks.",
        )

    def handle(self, *args, **options):
        users = _demo_users()
        report = collect_report(users)
        self._print_report(report)

        if options["check"]:
            self.stdout.write(self.style.SUCCESS("Check complete (no changes)."))
            return

        blockers = []
        if report["sessions_test"]:
            blockers.append(
                f"{report['sessions_test']} test CallSession(s) still linked "
                f"(run migrations first)."
            )
        if report["sessions_non_test"]:
            blockers.append(
                f"{report['sessions_non_test']} NON-TEST CallSession(s) still "
                f"linked (ids sample={report['non_test_session_ids']}). "
                f"Manual decision required before deletion."
            )
        if report["recordings"]:
            blockers.append(
                f"{report['recordings']} CallRecording(s) still have teacher_id "
                f"pointing at demo users."
            )
        fin = report["financial"]
        if isinstance(fin.get("subscriptions"), int) and fin["subscriptions"]:
            blockers.append(f"StudentSubscription rows={fin['subscriptions']}")
        if isinstance(fin.get("balances"), int) and fin["balances"]:
            blockers.append(f"StudentSubscriptionBalance rows={fin['balances']}")
        if report["rating_questions_demo"]:
            blockers.append(
                f"{report['rating_questions_demo']} RatingQuestion(s) still "
                f"category=demo_teacher (run migrations first)."
            )

        if blockers:
            raise CommandError(
                "Refusing --execute due to blockers:\n- " + "\n- ".join(blockers)
            )

        if not users:
            self.stdout.write(self.style.WARNING("No demo_teacher users found."))
            return

        with transaction.atomic():
            for user in users:
                self._delete_user_safely(user)

        remaining = _demo_users()
        if remaining:
            raise CommandError(
                f"Users still present after delete: {[u.username for u in remaining]}"
            )
        self.stdout.write(self.style.SUCCESS("demo_teacher account(s) deleted."))

    def _print_report(self, report: dict) -> None:
        self.stdout.write("=== remove_demo_teacher report ===")
        if report.get("schema_note"):
            self.stdout.write(self.style.WARNING(report["schema_note"]))
        if not report["users"]:
            self.stdout.write("users: (none)")
        for u in report["users"]:
            self.stdout.write(
                f"  user id={u.id} username={u.username!r} email={u.email!r}"
            )
        self.stdout.write(f"TeacherProfile: {report['profiles']}")
        self.stdout.write(f"TeacherAvailability: {report['availability']}")
        self.stdout.write(
            f"CallSession as teacher: total={report['sessions_total']} "
            f"test={report['sessions_test']} non_test={report['sessions_non_test']}"
        )
        if report["non_test_session_ids"]:
            self.stdout.write(
                f"  non_test sample ids: {report['non_test_session_ids']}"
            )
        self.stdout.write(f"CallRecording.teacher_id: {report['recordings']}")
        self.stdout.write(
            f"RatingQuestion category=demo_teacher: {report['rating_questions_demo']}"
        )
        self.stdout.write(f"financial: {report['financial']}")
        self.stdout.write("FK refs to demo users:")
        for table, col, n in report["fk_refs"]:
            self.stdout.write(f"  {table}.{col} = {n}")
        if not report["fk_refs"]:
            self.stdout.write("  (none)")

    def _delete_user_safely(self, user) -> None:
        """Delete known ownership rows explicitly; never rely on blind CASCADE."""
        TeacherAvailability.objects.filter(teacher_id=user.id).delete()
        TeacherProfile.objects.filter(user_id=user.id).delete()
        # M2M roles / groups
        if hasattr(user, "roles"):
            user.roles.clear()
        if hasattr(user, "groups"):
            user.groups.clear()
        if hasattr(user, "user_permissions"):
            user.user_permissions.clear()
        self.stdout.write(f"Deleting user id={user.id} username={user.username!r}")
        user.delete()
