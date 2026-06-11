"""
PostgreSQL Row-Level Security policies for tenant isolation.

On SQLite (development) this migration is a no-op — the ORM-level
TenantManager enforces tenancy at the application layer instead.

On PostgreSQL (staging / production) the database kernel independently
enforces the same boundary, so a bug or accidental bypass in Django
application code can never leak cross-tenant data.
"""
from django.db import migrations


def _apply_rls(cursor, table):
    cursor.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
    cursor.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
    cursor.execute(f'DROP POLICY IF EXISTS strict_tenant_isolation ON "{table}";')
    cursor.execute(f"""
        CREATE POLICY strict_tenant_isolation ON "{table}"
            AS RESTRICTIVE
            FOR ALL
            USING (
                school_id::text = current_setting('app.current_school_id', true)
                OR
                -- NULL setting = no tenant context (admin/superuser bypass, visitor flow)
                COALESCE(current_setting('app.current_school_id', true), '') = ''
            );
    """)


def _drop_rls(cursor, table):
    cursor.execute(f'DROP POLICY IF EXISTS strict_tenant_isolation ON "{table}";')
    cursor.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY;')


TABLES = [
    'notes_noteupload',
    'notes_conformityreport',
]


def apply_rls_policies(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            _apply_rls(cursor, table)


def drop_rls_policies(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        for table in TABLES:
            _drop_rls(cursor, table)


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0002_initial'),
    ]

    operations = [
        migrations.RunPython(
            apply_rls_policies,
            reverse_code=drop_rls_policies,
        ),
    ]
