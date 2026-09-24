import uuid

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone

import django.core.validators
import django.db.models.deletion


def add_custom_video_navigation(apps, schema_editor):
    NavigationItem = apps.get_model("content", "NavigationItem")
    NavigationItem.objects.update_or_create(
        location="header",
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
        location="header",
        label="Request Your Own Video",
        url="/request-your-own-video",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("content", "0007_live_class_booking"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomVideoServiceSettings",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False, help_text="Enable custom-video checkout only after a flat fee has been configured.")),
                ("flat_fee", models.DecimalField(blank=True, decimal_places=2, help_text="Admin-configured flat fee per custom-video request. No default price is assumed.", max_digits=10, null=True, validators=[django.core.validators.MinValueValidator(0)])),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                ("max_files", models.PositiveSmallIntegerField(default=5)),
                ("max_file_size_mb", models.PositiveSmallIntegerField(default=20)),
            ],
            options={"verbose_name": "Custom video service settings", "verbose_name_plural": "Custom video service settings"},
        ),
        migrations.CreateModel(
            name="CustomVideoRequest",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("reference", models.CharField(max_length=100, unique=True)),
                ("idempotency_key", models.CharField(editable=False, max_length=64, unique=True)),
                ("programme", models.CharField(choices=[("caps", "CAPS"), ("ieb", "IEB"), ("tvet", "TVET"), ("university", "University")], db_index=True, max_length=20)),
                ("subject", models.CharField(choices=[("mathematics", "Mathematics"), ("mathematical_literacy", "Mathematical Literacy")], db_index=True, max_length=32)),
                ("level", models.CharField(max_length=80)),
                ("topic", models.CharField(max_length=180)),
                ("amount", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("pending_payment", "Pending payment"), ("paid", "Paid"), ("in_progress", "In progress"), ("completed", "Completed"), ("cancelled", "Cancelled")], db_index=True, default="draft", max_length=20)),
                ("provider_reference", models.CharField(blank=True, max_length=160)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("gateway_verified_at", models.DateTimeField(blank=True, null=True)),
                ("invoice_number", models.CharField(blank=True, max_length=120, null=True, unique=True)),
                ("confirmation_sent_at", models.DateTimeField(blank=True, null=True)),
                ("admin_notification_sent_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_custom_video_requests", to=settings.AUTH_USER_MODEL)),
                ("student", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="custom_video_requests", to="content.studentrecord")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="customvideorequest", index=models.Index(fields=["student", "status", "-created_at"], name="video_req_student_status_idx")),
        migrations.AddIndex(model_name="customvideorequest", index=models.Index(fields=["status", "-created_at"], name="video_req_status_created_idx")),
        migrations.CreateModel(
            name="CustomVideoRequestFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("file", models.FileField(upload_to="custom-video-requests/%Y/%m/")),
                ("original_name", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("video_request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="supporting_files", to="content.customvideorequest")),
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
                ("amount", models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)])),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                ("issued_at", models.DateTimeField(default=timezone.now)),
                ("pdf", models.FileField(blank=True, upload_to="invoices/custom-video/%Y/%m/")),
                ("video_request", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="invoice", to="content.customvideorequest")),
            ],
            options={"ordering": ["-issued_at"]},
        ),
        migrations.RunPython(add_custom_video_navigation, remove_custom_video_navigation),
    ]
