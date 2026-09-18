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
                related_name="last_resumed_enrollments",
                to="content.lesson",
            ),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="last_position_seconds",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="progress_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
