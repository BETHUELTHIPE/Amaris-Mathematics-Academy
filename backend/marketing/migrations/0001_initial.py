from django.db import migrations, models
import django.db.models.deletion
import marketing.models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AnnouncementMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("media_type", models.CharField(choices=[("image", "Image"), ("video", "Video"), ("pdf", "PDF document")], max_length=8)),
                ("file", models.FileField(upload_to=marketing.models.marketing_upload_path)),
                ("caption", models.CharField(blank=True, max_length=220)),
                ("alt_text", models.CharField(blank=True, max_length=220)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("announcement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="marketing_media", to="content.announcement")),
            ],
            options={"ordering": ("order", "id"), "verbose_name_plural": "Announcement media"},
        ),
    ]
