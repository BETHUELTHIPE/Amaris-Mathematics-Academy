"""Tutor finance: contracts, encrypted destinations, immutable source ledger (no live payouts)."""

from decimal import Decimal
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
from django.core.validators import MaxValueValidator, MinValueValidator


def time_fields():
    return [
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("updated_at", models.DateTimeField(auto_now=True)),
    ]


def key_field():
    return [("id", models.BigAutoField(primary_key=True, serialize=False, auto_created=True, verbose_name="ID"))]


def tutor_fk(name, related_name):
    return (
        name,
        models.ForeignKey(
            to=settings.AUTH_USER_MODEL, related_name=related_name, on_delete=django.db.models.deletion.PROTECT
        ),
    )


service_choices = [("course", "Course sale"), ("live_class", "Online class"), ("video", "Topical video")]



def protect_finance_tables(apps, schema_editor):
    """Keep financial data outside Supabase's public Data API, including anon and authenticated roles."""
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in (
        "content_tutorpaymentprofile",
        "content_tutorcontract",
        "content_tutorcourseassignment",
        "content_tutorearning",
        "content_tutorpayout",
    ):
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
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL), ("content", "0012_tutor_recruitment")]

    operations = [
        migrations.CreateModel(
            name="TutorPaymentProfile",
            fields=key_field()
            + time_fields()
            + [
                ("account_holder", models.CharField(max_length=160, blank=True)),
                ("bank_name", models.CharField(max_length=100, blank=True)),
                ("branch_code", models.CharField(max_length=20, blank=True)),
                ("encrypted_account_number", models.TextField(blank=True, editable=False)),
                ("account_last_four", models.CharField(max_length=4, blank=True, editable=False)),
                (
                    "provider_recipient_id",
                    models.CharField(
                        max_length=120, blank=True, help_text="Verified recipient token, not an API secret."
                    ),
                ),
                ("recipient_verified_at", models.DateTimeField(null=True, blank=True)),
                (
                    "is_active",
                    models.BooleanField(default=False, help_text="Enable after bank ownership and contract checks."),
                ),
                (
                    "tutor",
                    models.OneToOneField(
                        to=settings.AUTH_USER_MODEL,
                        related_name="payment_profile",
                        on_delete=django.db.models.deletion.PROTECT,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="TutorContract",
            fields=key_field()
            + time_fields()
            + [
                ("service", models.CharField(max_length=20, choices=service_choices)),
                (
                    "tutor_percent",
                    models.DecimalField(
                        max_digits=5,
                        decimal_places=2,
                        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
                        help_text="Tutor percentage of gross sale: 60 means tutor 60%, Amaris 40%.",
                    ),
                ),
                ("effective_from", models.DateTimeField(default=django.utils.timezone.now)),
                ("effective_until", models.DateTimeField(null=True, blank=True)),
                ("is_active", models.BooleanField(default=True)),
                ("contract_reference", models.CharField(max_length=100, help_text="Signed agreement identifier")),
                tutor_fk("tutor", "finance_contracts"),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tutor", "service", "effective_from"), name="tutor_contract_start_unique"
                    )
                ]
            },
        ),
        migrations.CreateModel(
            name="TutorCourseAssignment",
            fields=key_field()
            + time_fields()
            + [
                ("is_active", models.BooleanField(default=True)),
                (
                    "course",
                    models.ForeignKey(
                        to="content.course",
                        related_name="tutor_assignments",
                        on_delete=django.db.models.deletion.PROTECT,
                    ),
                ),
                tutor_fk("tutor", "course_assignments"),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("course", "tutor"), name="tutor_course_unique")]},
        ),
        migrations.CreateModel(
            name="TutorEarning",
            fields=key_field()
            + time_fields()
            + [
                ("service", models.CharField(max_length=20, choices=service_choices)),
                ("source_reference", models.CharField(max_length=100)),
                ("service_label", models.CharField(max_length=180)),
                ("gross", models.DecimalField(max_digits=12, decimal_places=2)),
                ("tutor_percent", models.DecimalField(max_digits=5, decimal_places=2)),
                ("tutor_amount", models.DecimalField(max_digits=12, decimal_places=2)),
                ("academy_amount", models.DecimalField(max_digits=12, decimal_places=2)),
                ("currency", models.CharField(max_length=3, default="ZAR")),
                (
                    "state",
                    models.CharField(
                        max_length=12,
                        default="held",
                        db_index=True,
                        choices=[
                            ("held", "Held until delivery / settlement"),
                            ("ready", "Eligible for payout"),
                            ("paid", "Paid out"),
                            ("reversed", "Refunded / reversed"),
                        ],
                    ),
                ),
                ("payment_verified_at", models.DateTimeField()),
                ("service_delivered_at", models.DateTimeField(null=True, blank=True)),
                ("eligible_at", models.DateTimeField(null=True, blank=True)),
                (
                    "contract",
                    models.ForeignKey(
                        to="content.tutorcontract", related_name="earnings", on_delete=django.db.models.deletion.PROTECT
                    ),
                ),
                tutor_fk("tutor", "tutor_earnings"),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("service", "source_reference"), name="tutor_earning_source_unique")
                ],
                "indexes": [models.Index(fields=("tutor", "service", "state"), name="tutor_earnings_summary_idx")],
            },
        ),
        migrations.CreateModel(
            name="TutorPayout",
            fields=key_field()
            + time_fields()
            + [
                (
                    "state",
                    models.CharField(
                        max_length=20,
                        default="awaiting_provider",
                        choices=[
                            ("awaiting_provider", "Awaiting payout integration"),
                            ("processing", "Processing"),
                            ("paid", "Confirmed paid"),
                            ("failed", "Failed"),
                        ],
                    ),
                ),
                ("provider_name", models.CharField(max_length=60, blank=True)),
                ("provider_reference", models.CharField(max_length=160, blank=True)),
                ("bank_last_four", models.CharField(max_length=4, blank=True)),
                ("confirmed_at", models.DateTimeField(null=True, blank=True)),
                ("receipt_emailed_at", models.DateTimeField(null=True, blank=True)),
                ("failure_code", models.CharField(max_length=64, blank=True)),
                (
                    "earning",
                    models.OneToOneField(
                        to="content.tutorearning", related_name="payout", on_delete=django.db.models.deletion.PROTECT
                    ),
                ),
            ],
        ),
        migrations.RunPython(protect_finance_tables, migrations.RunPython.noop),
    ]
