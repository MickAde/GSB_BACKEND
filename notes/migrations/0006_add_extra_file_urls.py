from django.db import migrations, models


def add_extra_file_urls(apps, schema_editor):
    """
    PostgreSQL (Supabase): disable the 2-min statement timeout, then ADD COLUMN directly.
    SQLite / other: use schema_editor.add_field() so Django handles the dialect differences.
    """
    if schema_editor.connection.vendor == 'postgresql':
        with schema_editor.connection.cursor() as cur:
            cur.execute("SET statement_timeout = 0")
            cur.execute(
                "ALTER TABLE notes_noteupload "
                "ADD COLUMN IF NOT EXISTS extra_file_urls jsonb NOT NULL DEFAULT '[]'"
            )
    else:
        NoteUpload = apps.get_model('notes', 'NoteUpload')
        field = models.JSONField(blank=True, default=list)
        field.set_attributes_from_name('extra_file_urls')
        schema_editor.add_field(NoteUpload, field)


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('notes', '0005_add_doc_note_type'),
    ]

    operations = [
        # RunPython does the actual DDL for all DB backends.
        migrations.RunPython(add_extra_file_urls, migrations.RunPython.noop),
        # SeparateDatabaseAndState with no database_operations updates Django's
        # migration state without touching the DB (column already exists after RunPython).
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='noteupload',
                    name='extra_file_urls',
                    field=models.JSONField(blank=True, default=list),
                ),
            ],
        ),
    ]
