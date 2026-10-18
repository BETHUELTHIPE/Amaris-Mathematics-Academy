from django.db import migrations, models


def lock_down_rum_table(apps, schema_editor):
    """Disable Supabase Data API access to individual anonymous samples."""
    if schema_editor.connection.vendor != "postgresql":
        return
    name = schema_editor.quote_name("content_webvitalsample")
    schema_editor.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
    schema_editor.execute(f"REVOKE ALL ON TABLE {name} FROM PUBLIC")
    for role in ("anon", "authenticated"):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=%s)", [role])
            if cursor.fetchone()[0]:
                schema_editor.execute(f"REVOKE ALL ON TABLE {name} FROM {schema_editor.quote_name(role)}")


class Migration(migrations.Migration):
    dependencies = [("content", "0014_announcement_media")]

    operations = [
        migrations.CreateModel(
            name="WebVitalSample",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("metric_name", models.CharField(choices=[("LCP", "Largest Contentful Paint"), ("INP", "Interaction to Next Paint"), ("CLS", "Cumulative Layout Shift")], max_length=3)),
                ("value", models.FloatField()),
                ("page_group", models.CharField(max_length=24)),
                ("device", models.CharField(max_length=8)),
                ("observed_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "ordering": ("-observed_at",),
                "indexes": [
                    models.Index(fields=["metric_name", "observed_at"], name="rum_metric_observed_idx"),
                    models.Index(fields=["page_group", "observed_at"], name="rum_page_observed_idx"),
                ],
            },
        ),
        migrations.RunPython(lock_down_rum_table, migrations.RunPython.noop),
    ]
