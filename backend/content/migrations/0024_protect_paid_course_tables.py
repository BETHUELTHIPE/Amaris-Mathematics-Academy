from django.db import migrations


def secure_paid_course_tables(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        client_roles = [schema_editor.quote_name(role) for (role,) in cursor.fetchall()]
    for name in ("Course", "CourseModule", "Lesson", "VideoAsset", "ResourceAsset", "Enrollment", "Payment"):
        model = apps.get_model("content", name)
        table = schema_editor.quote_name(model._meta.db_table)
        schema_editor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM PUBLIC")
        if client_roles:
            schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM {', '.join(client_roles)}")


class Migration(migrations.Migration):
    dependencies = [("content", "0023_private_youtube_lesson_copy")]
    operations = [migrations.RunPython(secure_paid_course_tables, migrations.RunPython.noop)]
