from django.contrib.admin.apps import AdminConfig


class AmarisAdminConfig(AdminConfig):
    default_site = "amaris_cms.admin_site.AmarisAdminSite"
