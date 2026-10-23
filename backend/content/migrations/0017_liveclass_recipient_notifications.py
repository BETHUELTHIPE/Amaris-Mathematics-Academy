from django.db import migrations, models


def suppress_legacy_staff_notifications(apps, schema_editor):
    # Historic paid lessons are not new bookings; never email their tutors/admins retroactively.
    booking = apps.get_model("content", "LiveClassBooking")
    booking.objects.all().update(staff_notification_required=False)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0016_separate_location_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="liveclassbooking",
            name="tutor_confirmation_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="liveclassbooking",
            name="admin_confirmation_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="liveclassbooking",
            name="staff_notification_required",
            field=models.BooleanField(default=True, editable=False),
        ),
        migrations.RunPython(suppress_legacy_staff_notifications, migrations.RunPython.noop),
    ]
