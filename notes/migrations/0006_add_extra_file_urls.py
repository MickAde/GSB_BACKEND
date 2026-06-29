from django.db import migrations, models


def add_extra_file_urls(apps, schema_editor):
    """Add column with statement timeout disabled — Supabase enforces a short default."""
    with schema_editor.connection.cursor() as cur:
        cur.execute("SET statement_timeout = 0")
        cur.execute(
            "ALTER TABLE notes_noteupload "
            "ADD COLUMN IF NOT EXISTS extra_file_urls jsonb NOT NULL DEFAULT '[]'"
        )


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('notes', '0005_add_doc_note_type'),
    ]

    operations = [
        migrations.RunPython(add_extra_file_urls, migrations.RunPython.noop),
        # Keep AddField so Django's migration state stays in sync, but tell it the
        # column already exists (schema_editor.deferred_sql path skips IF NOT EXISTS)
        migrations.SeparateDatabaseAndState(
            database_operations=[],           # DB work done above
            state_operations=[
                migrations.AddField(
                    model_name='noteupload',
                    name='extra_file_urls',
                    field=models.JSONField(blank=True, default=list),
                ),
            ],
        ),
    ]
