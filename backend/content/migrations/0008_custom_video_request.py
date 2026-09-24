import decimal

import content.models
from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MinValueValidator
import django.utils.timezone


def add_custom_video_navigation(apps, schema_editor):
    NavigationItem = apps.get_model("content", "NavigationItem")
    NavigationItem.objects.update_or_create(
        location="both",
        label="Request Your Own Video",
        defaults={
            "url": "/request-your-own-video",
            "order": 27,
            "is_active": True,
            "open_in_new_tab": False,
        },
    )


def remove_custom_video_navigation(apps, schema_editor):
    NavigationItem = apps.get_model("content", "NavigationItem")
    NavigationItem.objects.filter(
        location="both",
        label="Request Your Own Video",
        url="/request-your-own-video",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0007_live_class_booking"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomVideoSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "enabled",
                    models.BooleanField(
                        default=False,
                        help_text="Enable custom-video requests only after a flat fee has been configured.",
                    ),
                ),
                (
                    "flat_fee",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Admin-configured price per custom-video request. No default price is assumed.",
                        max_digits=10,
                        null=True,
                        validators=[MinValueValidator(decimal.Decimal("0.01"))],
                    ),
                ),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                (
                    "max_files",
                    models.PositiveSmallIntegerField(
                        default=5,
                        help_text="Maximum number of supporting files accepted per request.",
                        validators=[MinValueValidator(1)],
                    ),
                ),
                (
                    "max_file_size_mb",
                    models.PositiveSmallIntegerField(
                        default=15,
                        help_text="Maximum size of each supporting file in megabytes.",
                        validators=[MinValueValidator(1)],
                    ),
                ),
            ],
            options={"verbose_name_plural": "Custom video settings"},
        ),
        migrations.CreateModel(
            name="CustomVideoRequest",
            fields=[
                ("id", models.UUIDField(default=content.models.uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("reference", models.CharField(max_length=100, unique=True)),
                ("idempotency_key", models.CharField(editable=False, max_length=64, unique=True)),
                (
                    "curriculum",
                    models.CharField(
                        choices=[
                            ("caps", "CAPS"),
                            ("ieb", "IEB"),
                            ("tvet", "TVET"),
                            ("university", "University"),
                        ],
                        db_index=True,
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
                        db_index=True,
                        max_length=32,
                    ),
                ),
                (
                    "grade",
                    models.CharField(
                        choices=[("10", "Grade 10"), ("11", "Grade 11"), ("12", "Grade 12")],
                        db_index=True,
                        max_length=2,
                    ),
                ),
                ("topic", models.CharField(max_length=220)),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_payment", "Pending payment"),
                            ("paid", "Paid"),
                            ("in_progress", "In progress"),
                            ("delivered", "Delivered"),
                            ("cancelled", "Cancelled"),
                        ],
                        db_index=True,
                        default="pending_payment",
                        max_length=20,
                    ),
                ),
                ("provider_reference", models.CharField(blank=True, max_length=160)),
                ("gateway_verified_at", models.DateTimeField(blank=True, null=True)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("invoice_sent_at", models.DateTimeField(blank=True, null=True)),
                ("delivery_url", models.URLField(blank=True)),
                ("admin_notes", models.TextField(blank=True)),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="custom_video_requests",
                        to="content.studentrecord",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="CustomVideoRequestAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "file",
                    models.FileField(upload_to=content.models.custom_video_attachment_upload_to),
                ),
                ("original_name", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("size_bytes", models.PositiveBigIntegerField()),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="content.customvideorequest",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="CustomVideoInvoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invoice_number", models.CharField(max_length=120, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                ("issued_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "pdf_file",
                    models.FileField(blank=True, upload_to="custom-video/invoices/%Y/%m/"),
                ),
                (
                    "request",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invoice",
                        to="content.customvideorequest",
                    ),
                ),
            ],
            options={"ordering": ["-issued_at"]},
        ),
        migrations.AddConstraint(
            model_name="customvideorequest",
            constraint=models.UniqueConstraint(
                condition=~models.Q(provider_reference=""),
                fields=("provider_reference",),
                name="cvideo_provider_ref_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="customvideorequest",
            index=models.Index(
                fields=["student", "status", "-created_at"],
                name="cvideo_student_status_idx",
            ),
        ),
        migrations.RunPython(
            add_custom_video_navigation,
            remove_custom_video_navigation,
        ),
    ]
