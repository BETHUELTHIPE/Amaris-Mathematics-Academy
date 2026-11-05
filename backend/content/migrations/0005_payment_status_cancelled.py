from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0004_payment_authority"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("paid", "Paid"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="pending",
                max_length=12,
            ),
        ),
    ]
