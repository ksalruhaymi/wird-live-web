from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from identity.accounts.auth.registration_service import username_from_email

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Set username to the email local-part (before @) for existing users. "
        "Skips when the target username is already taken by another account."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show planned changes without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        planned = []
        skipped = []
        conflicts = []

        users = User.objects.all().order_by("id")
        for user in users:
            email = (user.email or "").strip().lower()
            if not email:
                skipped.append((user.id, user.username, "no email"))
                continue

            target = username_from_email(email)
            if not target:
                skipped.append((user.id, user.username, "invalid email local-part"))
                continue

            if user.username == target:
                continue

            owner = (
                User.objects.filter(username__iexact=target)
                .exclude(pk=user.pk)
                .first()
            )
            if owner:
                conflicts.append(
                    (
                        user.id,
                        user.username,
                        target,
                        owner.id,
                        owner.username,
                    )
                )
                continue

            planned.append((user.id, user.username, target))

        if conflicts:
            self.stdout.write(self.style.ERROR("Conflicts (manual fix required):"))
            for uid, old, target, other_id, other_user in conflicts:
                self.stdout.write(
                    f"  user id={uid} username={old!r} -> {target!r} "
                    f"blocked by user id={other_id} username={other_user!r}"
                )

        if skipped:
            self.stdout.write(self.style.WARNING("Skipped:"))
            for uid, old, reason in skipped:
                self.stdout.write(f"  user id={uid} username={old!r}: {reason}")

        if not planned:
            self.stdout.write(self.style.SUCCESS("No username updates needed."))
            return

        self.stdout.write("Planned updates:")
        for uid, old, target in planned:
            self.stdout.write(f"  id={uid}: {old!r} -> {target!r}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only; no changes saved."))
            return

        with transaction.atomic():
            for uid, _old, target in planned:
                User.objects.filter(pk=uid).update(username=target)

        self.stdout.write(
            self.style.SUCCESS(f"Updated {len(planned)} user(s).")
        )
