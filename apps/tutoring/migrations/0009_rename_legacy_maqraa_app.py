from django.db import migrations


RENAME_TABLES_FORWARD = """
DO $$
BEGIN
  IF to_regclass('public.maqraa_teacherprofile') IS NOT NULL THEN
    ALTER TABLE maqraa_teacherprofile RENAME TO tutoring_teacherprofile;
  END IF;
  IF to_regclass('public.maqraa_studentprofile') IS NOT NULL THEN
    ALTER TABLE maqraa_studentprofile RENAME TO tutoring_studentprofile;
  END IF;
  IF to_regclass('public.maqraa_teacheravailability') IS NOT NULL THEN
    ALTER TABLE maqraa_teacheravailability RENAME TO tutoring_teacheravailability;
  END IF;
  IF to_regclass('public.maqraa_teacherfavorite') IS NOT NULL THEN
    ALTER TABLE maqraa_teacherfavorite RENAME TO tutoring_teacherfavorite;
  END IF;
  IF to_regclass('public.maqraa_maqraasession') IS NOT NULL THEN
    ALTER TABLE maqraa_maqraasession RENAME TO tutoring_session;
  ELSIF to_regclass('public.tutoring_maqraasession') IS NOT NULL THEN
    ALTER TABLE tutoring_maqraasession RENAME TO tutoring_session;
  END IF;
END $$;
"""

RENAME_TABLES_REVERSE = """
DO $$
BEGIN
  IF to_regclass('public.tutoring_session') IS NOT NULL THEN
    ALTER TABLE tutoring_session RENAME TO maqraa_maqraasession;
  END IF;
  IF to_regclass('public.tutoring_teacherfavorite') IS NOT NULL THEN
    ALTER TABLE tutoring_teacherfavorite RENAME TO maqraa_teacherfavorite;
  END IF;
  IF to_regclass('public.tutoring_teacheravailability') IS NOT NULL THEN
    ALTER TABLE tutoring_teacheravailability RENAME TO maqraa_teacheravailability;
  END IF;
  IF to_regclass('public.tutoring_studentprofile') IS NOT NULL THEN
    ALTER TABLE tutoring_studentprofile RENAME TO maqraa_studentprofile;
  END IF;
  IF to_regclass('public.tutoring_teacherprofile') IS NOT NULL THEN
    ALTER TABLE tutoring_teacherprofile RENAME TO maqraa_teacherprofile;
  END IF;
END $$;
"""

UPDATE_MIGRATIONS_FORWARD = """
UPDATE django_migrations SET app = 'tutoring' WHERE app = 'maqraa';
"""

UPDATE_MIGRATIONS_REVERSE = """
UPDATE django_migrations SET app = 'maqraa' WHERE app = 'tutoring';
"""

UPDATE_CONTENT_TYPES_FORWARD = """
UPDATE django_content_type
SET app_label = 'tutoring'
WHERE app_label = 'maqraa';
UPDATE django_content_type
SET model = 'tutoringsession'
WHERE app_label = 'tutoring' AND model = 'maqraasession';
"""

UPDATE_CONTENT_TYPES_REVERSE = """
UPDATE django_content_type
SET model = 'maqraasession'
WHERE app_label = 'tutoring' AND model = 'tutoringsession';
UPDATE django_content_type
SET app_label = 'maqraa'
WHERE app_label = 'tutoring';
"""

UPDATE_PERMISSIONS_FORWARD = """
UPDATE auth_permission
SET codename = REPLACE(codename, 'maqraasession', 'tutoringsession'),
    name = REPLACE(name, 'Maqraa session', 'Tutoring session')
WHERE content_type_id IN (
  SELECT id
  FROM django_content_type
  WHERE app_label = 'tutoring' AND model = 'tutoringsession'
);
"""

UPDATE_PERMISSIONS_REVERSE = """
UPDATE auth_permission
SET codename = REPLACE(codename, 'tutoringsession', 'maqraasession'),
    name = REPLACE(name, 'Tutoring session', 'Maqraa session')
WHERE content_type_id IN (
  SELECT id
  FROM django_content_type
  WHERE app_label = 'tutoring' AND model = 'tutoringsession'
);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tutoring", "0008_alter_teacherprofile_is_approved"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(RENAME_TABLES_FORWARD, RENAME_TABLES_REVERSE),
                migrations.RunSQL(UPDATE_MIGRATIONS_FORWARD, UPDATE_MIGRATIONS_REVERSE),
                migrations.RunSQL(
                    UPDATE_CONTENT_TYPES_FORWARD,
                    UPDATE_CONTENT_TYPES_REVERSE,
                ),
                migrations.RunSQL(
                    UPDATE_PERMISSIONS_FORWARD,
                    UPDATE_PERMISSIONS_REVERSE,
                ),
            ],
            state_operations=[
                migrations.RenameModel("MaqraaSession", "TutoringSession"),
                migrations.AlterModelTable(
                    name="teacherprofile",
                    table="tutoring_teacherprofile",
                ),
                migrations.AlterModelTable(
                    name="studentprofile",
                    table="tutoring_studentprofile",
                ),
                migrations.AlterModelTable(
                    name="teacheravailability",
                    table="tutoring_teacheravailability",
                ),
                migrations.AlterModelTable(
                    name="teacherfavorite",
                    table="tutoring_teacherfavorite",
                ),
                migrations.AlterModelTable(
                    name="tutoringsession",
                    table="tutoring_session",
                ),
            ],
        ),
    ]
