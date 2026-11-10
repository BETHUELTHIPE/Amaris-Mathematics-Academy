from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("content", "0008_announcement_media")]

    operations = [
        migrations.AddField(
            model_name="liveclassbooking",
            name="payment_provider",
            field=models.CharField(
                max_length=16, default="payfast",
                choices=[("payfast", "PayFast"), ("paystack", "Paystack")],
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="provider",
            field=models.CharField(
                max_length=16,
                choices=[
                    ("payfast", "PayFast"),
                    ("paystack", "Paystack"),
                    ("google_pay", "Google Pay"),
                ],
            ),
        ),
    ]
