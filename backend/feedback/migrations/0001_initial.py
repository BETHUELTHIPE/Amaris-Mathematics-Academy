import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [("content", "__first__")]
    operations = [
        migrations.CreateModel(
            name="HappyForm",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("service", models.CharField(max_length=20, choices=[("live_class", "Zoom online lesson"), ("course", "Course or learning materials")])),
                ("service_reference", models.CharField(max_length=100)),
                ("service_title", models.CharField(max_length=200)),
                ("tutor_name", models.CharField(max_length=160, blank=True)),
                ("overall_rating", models.PositiveSmallIntegerField()),
                ("tutor_rating", models.PositiveSmallIntegerField(null=True, blank=True)),
                ("comments", models.TextField(max_length=1000, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("archive_path", models.CharField(max_length=300, blank=True)),
                ("archived_at", models.DateTimeField(null=True, blank=True)),
                ("admin_emailed_at", models.DateTimeField(null=True, blank=True)),
                ("student", models.ForeignKey(to="content.studentrecord", on_delete=django.db.models.deletion.PROTECT, related_name="happy_forms")),
            ],
            options={"verbose_name": "Happy form", "verbose_name_plural": "Happy forms", "ordering": ("-created_at",)},
        ),
        migrations.AddConstraint(model_name="happyform", constraint=models.UniqueConstraint(fields=("student", "service", "service_reference"), name="one_happy_form_per_service")),
    ]
