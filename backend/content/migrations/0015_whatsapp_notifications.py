from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0008_announcement_media"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WhatsAppPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=20, help_text="E.164 number, e.g. +27821234567")),
                ("opted_in", models.BooleanField(default=False)),
                ("consent_recorded_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("student", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_preference", to="content.studentrecord")),
                ("tutor", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_preference", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="whatsapppreference",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(student__isnull=False, tutor__isnull=True)
                    | models.Q(student__isnull=True, tutor__isnull=False)
                ), name="whatsapp_exactly_one_recipient",
            ),
        ),
        migrations.CreateModel(
            name="WhatsAppDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=20, choices=[("confirmation", "Booking confirmation"), ("reminder", "30-minute reminder")])),
                ("slot_start", models.DateTimeField()),
                ("status", models.CharField(max_length=12, default="pending", choices=[("pending", "Pending"), ("sent", "Accepted by provider"), ("skipped", "Skipped"), ("failed", "Failed")])),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("provider_id", models.CharField(blank=True, max_length=128)),\n                ("receipt_status", models.CharField(blank=True, max_length=16, default="")),
                ("error_code", models.CharField(blank=True, max_length=80)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("booking", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="whatsapp_deliveries", to="content.liveclassbooking")),
                ("preference", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="content.whatsapppreference")),
            ],
        ),
        migrations.AddConstraint(
            model_name="whatsappdelivery",
            constraint=models.UniqueConstraint(
                fields=["booking", "preference", "kind", "slot_start"],
                name="whatsapp_unique_booking_event",
            ),
        ),
    ]
