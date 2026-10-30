from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("feedback", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="FeedbackFollowUp",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("status", models.CharField(max_length=20, default="pending", choices=[("pending", "Awaiting call"), ("contacted", "Student contacted"), ("resolved", "Resolved"), ("unreachable", "Unable to reach student")])),
                ("due_at", models.DateTimeField(db_index=True)),
                ("reminder_sent_at", models.DateTimeField(null=True, blank=True)),
                ("contacted_at", models.DateTimeField(null=True, blank=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("feedback", models.OneToOneField(to="feedback.happyform", on_delete=django.db.models.deletion.PROTECT, related_name="followup")),
            ],
            options={"verbose_name": "Student follow-up", "verbose_name_plural": "Student follow-ups", "ordering": ("due_at",)},
        ),
    ]
