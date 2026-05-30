from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = "Run all seed and import commands in the correct order."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("🚀 Starting seed_all...\n"))

        commands = [
            "seed_superadmin",
            "seed_rbac",
            "import_quran_data",
            "import_qurra",
            "import_tafsir_books",
            "import_tafsir",
            "import_ayah_positions",
            "import_ayah_wordmeaning",
            "import_hifz_thematic_data",
        ]

        for command_name in commands:
            try:
                self.stdout.write(self.style.WARNING(f"➡ Running {command_name}"))
                call_command(command_name)
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ Failed: {command_name} → {e}")
                )

        self.stdout.write(self.style.SUCCESS("\n✅ All seed/import commands finished."))