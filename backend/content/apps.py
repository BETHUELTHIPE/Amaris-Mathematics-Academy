from django.apps import AppConfig


class ContentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "content"
    verbose_name = "Academy content"

    def ready(self):
        from . import admin_users  # noqa: F401
        from . import signals  # noqa: F401
