from django.contrib.admin.apps import AdminConfig


class AmarisAdminConfig(AdminConfig):
    """Use the Amaris admin site with superuser-only monitoring."""

    default_site = "amaris_cms.monitoring_admin.AmarisAdminSite"
