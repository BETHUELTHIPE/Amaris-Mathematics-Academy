from django.db import migrations, models

import content.private_media_storage


class Migration(migrations.Migration):
    dependencies = [("content", "0004_limit_contact_enquiry_message")]

    operations = [
        migrations.AlterField(
            model_name="videoasset",
            name="provider",
            field=models.CharField(
                choices=[
                    ("youtube", "Private YouTube"),
                    ("s3", "Private S3 upload"),
                    ("vimeo", "Private Vimeo"),
                ],
                default="youtube",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="videoasset",
            name="vimeo_video_id",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="videoasset",
            name="vimeo_url",
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name="videoasset",
            name="aws_file",
            field=models.FileField(
                blank=True,
                storage=content.private_media_storage.private_video_storage,
                upload_to="private-videos/%Y/%m/",
            ),
        ),
    ]
