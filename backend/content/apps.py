# ruff: noqa: F401
from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "content"
    verbose_name = "Academy content"

    def import_models(self):
        super().import_models()
        from . import payment_models, subscription_models, subscription_report_models, tutor_finance_models

    def ready(self):
        from . import payment_admin, schema, signals, subscription_admin, subscription_report_admin, tutor_finance_admin
