from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "content"
    verbose_name = "Academy content"

    def import_models(self):
        super().import_models()
        from . import donation_models, payment_models, tutor_finance_models  # noqa: F401

    def ready(self):
        from . import donation_admin, payment_admin, schema, signals, tutor_finance_admin  # noqa: F401
