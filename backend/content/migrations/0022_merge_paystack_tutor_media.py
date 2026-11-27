"""Merge independently developed Paystack and tutor media migrations."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0020_liveclass_paystack"),
        ("content", "0021_tutor_video_submissions"),
    ]

    operations = []
