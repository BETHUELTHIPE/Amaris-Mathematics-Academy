from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0005_payment_status_cancelled"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="last_lesson",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="resume_enrollments",
                to="content.lesson",
            ),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="last_position_seconds",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="notificationoutbox",
            name="attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="notificationoutbox",
            name="last_error_code",
            field=models.CharField(blank=True, editable=False, max_length=80),
        ),
        migrations.AlterField(
            model_name="notificationoutbox",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("sending", "Sending"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                ],
                db_index=True,
                default="queued",
                max_length=12,
            ),
        ),
    ]
