from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content", "0008_announcement_media")]

    operations = [
        migrations.AlterField(
            model_name="liveclassbooking",
            name="provider_reference",
            field=models.CharField(blank=True, db_index=True, max_length=160),
        ),
        migrations.AddIndex(
            model_name="liveclassbooking",
            index=models.Index(
                fields=("paid_at", "created_at"),
                condition=models.Q(
                    status="confirmed", confirmation_sent_at__isnull=True
                ),
                name="liveclass_confirm_q_idx",
            ),
        ),
    ]
