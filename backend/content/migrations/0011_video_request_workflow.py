import uuid

from django.conf import settings
from django.db import migrations, models

import content.models
import django.core.validators
import django.db.models.deletion


def add_video_request_navigation(apps, schema_editor):
    NavigationItem = apps.get_model("content", "NavigationItem")
    NavigationItem.objects.update_or_create(
        location="both",
        label="Request a video",
        defaults={
            "url": "/request-a-video",
            "order": 24,
            "is_active": True,
            "open_in_new_tab": False,
        },
    )


def remove_video_request_navigation(apps, schema_editor):
    NavigationItem = apps.get_model("content", "NavigationItem")
    NavigationItem.objects.filter(
        location="both",
        label="Request a video",
        url="/request-a-video",
    ).delete()


def protect_video_request_tables(apps, schema_editor):
    del apps
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("content_videorequest", "content_videorequestdocument"):
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
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("content", "0010_private_booking_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="VideoRequest",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "id",
                    models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False),
                ),
                ("reference", models.CharField(max_length=100, unique=True)),
                ("idempotency_key", models.CharField(editable=False, max_length=64, unique=True)),
                (
                    "programme",
                    models.CharField(
                        choices=[
                            ("caps", "CAPS"),
                            ("ieb", "IEB"),
                            ("tvet", "TVET"),
                            ("university", "University"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "subject",
                    models.CharField(
                        choices=[
                            ("mathematics", "Mathematics"),
                            ("mathematical_literacy", "Mathematical Literacy"),
                        ],
                        max_length=32,
                    ),
                ),
                ("level", models.CharField(max_length=80)),
                ("topic", models.CharField(max_length=180)),
                (
                    "request_type",
                    models.CharField(
                        choices=[
                            ("chapter_topic", "Chapter or topic video"),
                            ("previous_assignment", "Previous assignment walkthrough"),
                            ("previous_exam", "Previous exam walkthrough"),
                            ("complete_content", "Complete subject content"),
                        ],
                        max_length=24,
                    ),
                ),
                ("instructions", models.TextField(blank=True)),
                ("explanation_style", models.CharField(blank=True, max_length=120)),
                ("preferred_duration_minutes", models.PositiveSmallIntegerField(default=60)),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_payment", "Pending payment"),
                            ("queued", "Paid and queued"),
                            ("tutor_assigned", "Tutor assigned"),
                            ("recording", "Recording"),
                            ("processing", "Processing"),
                            ("review", "Quality review"),
                            ("ready", "Ready"),
                            ("cancelled", "Cancelled"),
                            ("payment_review", "Payment requiring review"),
                        ],
                        db_index=True,
                        default="pending_payment",
                        max_length=20,
                    ),
                ),
                (
                    "payment_expires_at",
                    models.DateTimeField(db_index=True, default=content.models.video_request_payment_expiry),
                ),
                ("provider_reference", models.CharField(blank=True, max_length=160)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("gateway_verified_at", models.DateTimeField(blank=True, null=True)),
                ("queue_entered_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("priority_paid_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("ticket_number", models.CharField(blank=True, max_length=120, null=True, unique=True)),
                ("invoice_number", models.CharField(blank=True, max_length=120, null=True, unique=True)),
                (
                    "video_provider",
                    models.CharField(
                        choices=[("youtube", "YouTube unlisted"), ("direct", "Private direct video")],
                        default="youtube",
                        max_length=12,
                    ),
                ),
                (
                    "video_external_id",
                    models.CharField(
                        blank=True,
                        help_text="Store only the provider ID or private object key, never a public URL.",
                        max_length=160,
                    ),
                ),
                ("video_ready_at", models.DateTimeField(blank=True, null=True)),
                ("confirmation_sent_at", models.DateTimeField(blank=True, null=True)),
                ("position_one_sent_at", models.DateTimeField(blank=True, null=True)),
                ("recording_sent_at", models.DateTimeField(blank=True, null=True)),
                ("ready_notification_sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "assigned_tutor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_video_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="video_requests",
                        to="content.studentrecord",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="videorequest",
            index=models.Index(fields=["student", "status", "-created_at"], name="video_req_student_idx"),
        ),
        migrations.AddIndex(
            model_name="videorequest",
            index=models.Index(fields=["status", "queue_entered_at"], name="video_req_queue_idx"),
        ),
        migrations.AddIndex(
            model_name="videorequest",
            index=models.Index(fields=["status", "payment_expires_at"], name="video_req_expiry_idx"),
        ),
        migrations.CreateModel(
            name="VideoRequestDocument",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("original_name", models.CharField(max_length=255)),
                ("storage_path", models.CharField(editable=False, max_length=512, unique=True)),
                ("content_type", models.CharField(max_length=100)),
                ("size_bytes", models.PositiveIntegerField()),
                ("sha256", models.CharField(editable=False, max_length=64)),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="content.videorequest",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddIndex(
            model_name="videorequestdocument",
            index=models.Index(fields=["request", "created_at"], name="video_req_doc_idx"),
        ),
        migrations.RunPython(add_video_request_navigation, remove_video_request_navigation),
        migrations.RunPython(protect_video_request_tables, migrations.RunPython.noop),
    ]

