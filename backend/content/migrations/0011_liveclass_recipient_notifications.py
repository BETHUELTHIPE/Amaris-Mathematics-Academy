from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0010_private_booking_tables"),
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
