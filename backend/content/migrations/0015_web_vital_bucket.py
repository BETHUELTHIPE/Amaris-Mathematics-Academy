from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content", "0014_announcement_media")]

    operations = [
        migrations.CreateModel(
            name="WebVitalBucket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("day", models.DateField()),
                ("metric", models.CharField(max_length=3)),
                ("route", models.CharField(max_length=24)),
                ("device", models.CharField(max_length=8)),
                ("network", models.CharField(max_length=8)),
                ("bucket", models.PositiveSmallIntegerField()),
                ("count", models.PositiveIntegerField(default=0)),
            ],
            options={
                "verbose_name": "Anonymous daily Web Vital bucket",
                "verbose_name_plural": "Anonymous daily Web Vital buckets",
            },
        ),
        migrations.AddConstraint(
            model_name="webvitalbucket",
            constraint=models.UniqueConstraint(
                fields=("day", "metric", "route", "device", "network", "bucket"),
                name="rum_daily_bucket_unique",
            ),
        ),
        migrations.AddIndex(
            model_name="webvitalbucket",
            index=models.Index(fields=["-day", "metric"], name="rum_day_metric_idx"),
        ),
    ]
