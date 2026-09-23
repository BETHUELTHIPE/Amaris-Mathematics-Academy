import datetime
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def add_live_class_navigation(apps, schema_editor):
    NavigationItem = apps.get_model("content", "NavigationItem")
    NavigationItem.objects.update_or_create(
        location="both",
        label="Book online live class",
        defaults={
            "url": "/book-online-live-class",
            "order": 25,
            "is_active": True,
            "open_in_new_tab": False,
        },
    )


def remove_live_class_navigation(apps, schema_editor):
    NavigationItem = apps.get_model("content", "NavigationItem")
    NavigationItem.objects.filter(
        location="both",
        label="Book online live class",
        url="/book-online-live-class",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("content", "0006_enrollment_resume"),
    ]

    operations = [
        migrations.CreateModel(
            name="TutorAvailabilitySlot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "programme",
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
                ("level", models.CharField(db_index=True, max_length=80)),
                ("starts_at", models.DateTimeField(db_index=True)),
                ("ends_at", models.DateTimeField()),
                ("zoom_join_url", models.URLField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "tutor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="live_class_slots",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": [
                    "starts_at",
                    "tutor__first_name",
                    "tutor__last_name",
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="tutoravailabilityslot",
            constraint=models.UniqueConstraint(
                fields=("tutor", "starts_at"),
                name="liveclass_tutor_start_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="tutoravailabilityslot",
            index=models.Index(
                fields=["programme", "subject", "level", "starts_at"],
                name="liveclass_slot_lookup_idx",
            ),
        ),
        migrations.CreateModel(
            name="LiveClassBooking",
            fields=[
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("reference", models.CharField(max_length=100, unique=True)),
                (
                    "idempotency_key",
                    models.CharField(editable=False, max_length=64, unique=True),
                ),
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
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        default="250.00",
                        max_digits=10,
                    ),
                ),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending_payment", "Pending payment"),
                            ("confirmed", "Confirmed"),
                            ("expired", "Expired"),
                            ("cancelled", "Cancelled"),
                            ("completed", "Completed"),
                        ],
                        db_index=True,
                        default="pending_payment",
                        max_length=20,
                    ),
                ),
                (
                    "hold_expires_at",
                    models.DateTimeField(
                        db_index=True,
                        default=datetime.datetime.now,
                    ),
                ),
                ("provider_reference", models.CharField(blank=True, max_length=160)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                (
                    "gateway_verified_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "invoice_number",
                    models.CharField(
                        blank=True,
                        max_length=120,
                        null=True,
                        unique=True,
                    ),
                ),
                (
                    "confirmation_sent_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "reminder_sent_at",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "slot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bookings",
                        to="content.tutoravailabilityslot",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="live_class_bookings",
                        to="content.studentrecord",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="liveclassbooking",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("status__in", ("pending_payment", "confirmed")),
                ),
                fields=("slot",),
                name="liveclass_active_slot_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="liveclassbooking",
            index=models.Index(
                fields=["student", "status", "-created_at"],
                name="liveclass_student_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="liveclassbooking",
            index=models.Index(
                fields=["status", "hold_expires_at"],
                name="liveclass_hold_status_idx",
            ),
        ),
        migrations.RunPython(
            add_live_class_navigation,
            remove_live_class_navigation,
        ),
    ]
