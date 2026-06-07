from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run all seed commands in the correct order."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting seed_all...\n"))

        commands = [
            "seed_superadmin",
            "seed_rbac",
            "seed_demo_teacher",
        ]

        for command_name in commands:
            try:
                self.stdout.write(self.style.WARNING(f"Running {command_name}"))
                call_command(command_name)
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed: {command_name} -> {e}")
                )

        self.stdout.write(self.style.SUCCESS("\nAll seed commands finished."))
