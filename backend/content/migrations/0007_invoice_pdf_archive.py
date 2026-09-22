from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0006_enrollment_resume"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="pdf_storage_path",
            field=models.CharField(blank=True, editable=False, max_length=512),
        ),
        migrations.AddField(
            model_name="invoice",
            name="pdf_sha256",
            field=models.CharField(blank=True, editable=False, max_length=64),
        ),
        migrations.AddField(
            model_name="invoice",
            name="pdf_generated_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="invoice",
            name="pdf_last_error_code",
            field=models.CharField(blank=True, editable=False, max_length=120),
        ),
    ]
