from django.db import migrations


def protect_booking_tables(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("content_tutoravailabilityslot", "content_liveclassbooking"):
        quoted_table = schema_editor.quote_name(table)
        schema_editor.execute(f"ALTER TABLE {quoted_table} ENABLE ROW LEVEL SECURITY")
        for role in ("anon", "authenticated"):
            with schema_editor.connection.cursor() as cursor:
                cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = %s)", [role])
                exists = cursor.fetchone()[0]
            if exists:
                schema_editor.execute(
                    f"REVOKE ALL ON TABLE {quoted_table} FROM {schema_editor.quote_name(role)}"
                )


class Migration(migrations.Migration):
    dependencies = [("content", "0009_merge_invoice_booking")]
    operations = [migrations.RunPython(protect_booking_tables, migrations.RunPython.noop)]
