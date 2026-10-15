import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content", "0007_live_class_booking")]

    operations = [
        migrations.CreateModel(
            name="AnnouncementMedia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("kind", models.CharField(choices=[("image", "Image"), ("video", "Video"), ("pdf", "PDF")], max_length=8)),
                ("title", models.CharField(max_length=180)),
                ("file", models.FileField(upload_to="marketing/announcements/%Y/%m/")),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("announcement", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="media", to="content.announcement")),
            ],
            options={"ordering": ("order", "id")},
        ),
    ]
