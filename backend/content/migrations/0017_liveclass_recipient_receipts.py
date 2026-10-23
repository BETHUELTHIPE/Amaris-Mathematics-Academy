# Generated for per-recipient live-class booking notification receipts.

from django.db import migrations, models


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
    ]
