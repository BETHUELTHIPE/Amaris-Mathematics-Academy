from django.contrib.admin.apps import AdminConfig


class AmarisAdminConfig(AdminConfig):
    """Use an admin site that exposes monitoring only to superusers."""

    default_site = "amaris_cms.monitoring_admin.AmarisAdminSite"
