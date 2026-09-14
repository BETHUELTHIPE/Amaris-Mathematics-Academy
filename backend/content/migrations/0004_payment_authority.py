import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0003_announcement_announcement_live_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PaymentWebhookEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("provider", models.CharField(default="payfast", max_length=16)),
                ("provider_reference", models.CharField(max_length=160)),
                ("payment_status", models.CharField(max_length=32)),
                ("local_reference", models.CharField(max_length=100)),
                ("payload_hash", models.CharField(blank=True, editable=False, max_length=64)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("received", "Received"),
                            ("retryable", "Retryable"),
                            ("processed", "Processed"),
                            ("rejected", "Rejected"),
                        ],
                        db_index=True,
                        default="received",
                        max_length=16,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("last_error_code", models.CharField(blank=True, editable=False, max_length=80)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "payment",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="webhook_events",
                        to="content.payment",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invoice_number", models.CharField(max_length=120, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("currency", models.CharField(default="ZAR", max_length=3)),
                ("issued_at", models.DateTimeField()),
                (
                    "course",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invoices",
                        to="content.course",
                    ),
                ),
                (
                    "payment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invoice",
                        to="content.payment",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invoices",
                        to="content.studentrecord",
                    ),
                ),
            ],
            options={"ordering": ["-issued_at"]},
        ),
        migrations.CreateModel(
            name="ServiceTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("ticket_number", models.CharField(max_length=120, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("fulfilled", "Fulfilled")],
                        db_index=True,
                        default="fulfilled",
                        max_length=16,
                    ),
                ),
                (
                    "enrollment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="service_tickets",
                        to="content.enrollment",
                    ),
                ),
                (
                    "payment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="service_ticket",
                        to="content.payment",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="NotificationOutbox",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_type", models.CharField(default="payment_success", max_length=40)),
                ("destination", models.EmailField(max_length=254)),
                (
                    "status",
                    models.CharField(
                        choices=[("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed")],
                        db_index=True,
                        default="queued",
                        max_length=12,
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                (
                    "payment",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="success_notification",
                        to="content.payment",
                    ),
                ),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="paymentwebhookevent",
            constraint=models.UniqueConstraint(
                fields=("provider", "provider_reference", "payment_status"),
                name="pay_webhook_provider_status_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="paymentwebhookevent",
            index=models.Index(fields=["state", "-created_at"], name="pay_webhook_state_time_idx"),
        ),
        migrations.AddIndex(
            model_name="paymentwebhookevent",
            index=models.Index(fields=["local_reference"], name="pay_webhook_local_ref_idx"),
        ),
        migrations.AddIndex(
            model_name="notificationoutbox",
            index=models.Index(fields=["status", "created_at"], name="notify_outbox_status_idx"),
        ),
    ]
