"""Select private storage without touching existing columns or file keys."""

import amaris_cms.storage
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0026_admin_fortnightly_performance"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AlterField(
                    model_name="performancedigest",
                    name="pdf",
                    field=models.FileField(
                        editable=False,
                        max_length=250,
                        storage=amaris_cms.storage.tutor_private_storage,
                        upload_to="",
                    ),
                ),
                migrations.AlterField(
                    model_name="tutorpersonnelform",
                    name="pdf",
                    field=models.FileField(
                        editable=False,
                        max_length=250,
                        storage=amaris_cms.storage.tutor_private_storage,
                        upload_to="",
                    ),
                ),
            ],
        ),
    ]
