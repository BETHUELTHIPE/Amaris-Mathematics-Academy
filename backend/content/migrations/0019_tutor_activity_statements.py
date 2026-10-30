"""Add private per-tutor 30-day report snapshots, without affecting payout records."""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("content", "0018_tutor_document_categories"),
    ]
    operations = [
        migrations.CreateModel(
            name="TutorActivityStatement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("period_start", models.DateTimeField()),
                ("period_end", models.DateTimeField()),
                ("report_number", models.CharField(max_length=96, unique=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("draft", "Draft / awaiting archive"),
                            ("archived", "Archived / awaiting delivery"),
                            ("delivered", "Tutor and administrator notified"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=16,
                    ),
                ),
                ("snapshot", models.JSONField(default=dict, editable=False)),
                ("pdf_storage_path", models.CharField(blank=True, editable=False, max_length=512)),
                ("pdf_sha256", models.CharField(blank=True, editable=False, max_length=64)),
                ("tutor_emailed_at", models.DateTimeField(blank=True, editable=False, null=True)),
                ("admin_emailed_at", models.DateTimeField(blank=True, editable=False, null=True)),
                (
                    "tutor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="activity_statements",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-period_end", "tutor_id"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tutor", "period_start", "period_end"), name="tutor_stmt_unique_period"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("period_end__gt", models.F("period_start"))), name="tutor_stmt_valid_period"
                    ),
                ],
                "indexes": [models.Index(fields=("state", "period_end"), name="tutor_stmt_pending_idx")],
            },
        ),
    ]
