from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0008_custom_video_request"),
    ]

    operations = [
        migrations.AddField(
            model_name="customvideorequest",
            name="delivery_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
