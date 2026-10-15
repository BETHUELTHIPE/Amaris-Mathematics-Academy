import django.db.models.deletion
from django.db import migrations, models


def secure_announcement_media(apps, schema_editor):
    """Prevent the public Data API roles from reading private S3 object paths."""
    if schema_editor.connection.vendor != "postgresql":
        return
    quoted = schema_editor.quote_name("content_announcementmedia")
    schema_editor.execute(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY")
    schema_editor.execute(f"REVOKE ALL ON TABLE {quoted} FROM PUBLIC")
    for role in ("anon", "authenticated"):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = %s)", [role])
            exists = cursor.fetchone()[0]
        if exists:
            schema_editor.execute(f"REVOKE ALL ON TABLE {quoted} FROM {schema_editor.quote_name(role)}")


class Migration(migrations.Migration):
    dependencies = [("content", "0013_tutor_finance")]

    operations = [
        migrations.CreateModel(
            name="AnnouncementMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("kind", models.CharField(choices=[("image", "Image"), ("video", "Video"), ("pdf", "PDF")], max_length=8)),
                ("title", models.CharField(max_length=180)),
                ("file", models.FileField(upload_to="marketing/announcements/%Y/%m/")),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("announcement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="media", to="content.announcement")),
            ],
            options={"ordering": ("order", "id")},
        ),        migrations.RunPython(secure_announcement_media, migrations.RunPython.noop),
    ]
