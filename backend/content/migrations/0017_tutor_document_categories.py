from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0016_separate_location_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="tutorapplicationdocument",
            name="category",
            field=models.CharField(
                choices=[
                    ("legacy", "Legacy qualification"),
                    ("id", "Identity document"),
                    ("cv", "Curriculum vitae"),
                    ("matric", "Matric certificate"),
                    ("academic", "Academic records"),
                    ("tertiary", "Tertiary certificate"),
                    ("other", "Additional document"),
                ],
                default="legacy",
                max_length=16,
            ),
        ),
    ]
