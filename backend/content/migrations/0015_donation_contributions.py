from django.db import migrations, models
import django.db.models.deletion
import uuid


def deny_public_donation_table_access(apps, schema_editor):
    """Only the Django server and privileged operations may read donor records."""
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("content_donationcontribution",):
        quoted = schema_editor.quote_name(table)
        schema_editor.execute(f"ALTER TABLE {quoted} ENABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {quoted} FROM PUBLIC")
        for role in ("anon", "authenticated"):
            with schema_editor.connection.cursor() as cursor:
                cursor.execute("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = %s)", [role])
                exists = cursor.fetchone()[0]
            if exists:
                schema_editor.execute(f"REVOKE ALL ON TABLE {quoted} FROM {schema_editor.quote_name(role)}")


class Migration(migrations.Migration):
    dependencies = [("content", "0014_announcement_media")]

    operations = [
        migrations.CreateModel(
            name="DonationContribution",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(editable=False, max_length=44, unique=True)),
                ("donor_name", models.CharField(max_length=100)),
                ("donor_email", models.EmailField(max_length=254)),
                ("purpose", models.CharField(choices=[
                    ("learner", "Support a learner"),
                    ("resources", "Learning resources"),
                    ("technology", "Technology and accessibility"),
                    ("general", "General education project"),
                ], max_length=16)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=9)),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                ("status", models.CharField(choices=[
                    ("pending", "Awaiting verification"), ("paid", "Verified by PayFast"),
                    ("failed", "Failed"), ("cancelled", "Cancelled"),
                ], db_index=True, default="pending", max_length=12)),
                ("provider_reference", models.CharField(blank=True, editable=False, max_length=160, null=True, unique=True)),
                ("gateway_verified_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("paid_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("receipt_sent_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("receipt_error", models.CharField(blank=True, editable=False, max_length=60)),
                ("last_callback_status", models.CharField(blank=True, editable=False, max_length=16)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AddIndex(
            model_name="donationcontribution",
            index=models.Index(fields=["status", "-created_at"], name="donation_status_created_idx"),
        ),
        migrations.RunPython(deny_public_donation_table_access, migrations.RunPython.noop),
    ]
