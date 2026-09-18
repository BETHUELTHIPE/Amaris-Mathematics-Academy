import os

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.db.models.signals import post_delete, post_migrate, post_save
from django.dispatch import receiver

from .models import (
    FAQ,
    Announcement,
    Course,
    CourseCategory,
    CourseModule,
    Lesson,
    NavigationItem,
    Page,
    PageSection,
    PricingPlan,
    SiteSettings,
    Testimonial,
)

PUBLIC_CONTENT_MODELS = (
    SiteSettings,
    NavigationItem,
    Page,
    PageSection,
    CourseCategory,
    Course,
    CourseModule,
    Lesson,
    PricingPlan,
    Testimonial,
    FAQ,
    Announcement,
)


@receiver(post_save, sender=None, dispatch_uid="content.invalidate_public_cache_on_save")
@receiver(post_delete, sender=None, dispatch_uid="content.invalidate_public_cache_on_delete")
def invalidate_public_cache(sender, **_kwargs):
    if sender in PUBLIC_CONTENT_MODELS:
        caches["public_content"].clear()


@receiver(post_migrate, dispatch_uid="content.ensure_environment_admin")
def ensure_environment_admin(**_kwargs):
    """Create or repair the deployment administrator from runtime-only secrets.

    The password is never stored in source control. Set
    DJANGO_ADMIN_RESET_PASSWORD=true only for an intentional one-time reset,
    then turn it off so later deploys do not overwrite an administrator's
    changed password.
    """

    username = os.getenv("DJANGO_ADMIN_USERNAME", "").strip()
    password = os.getenv("DJANGO_ADMIN_PASSWORD", "")
    email = os.getenv("DJANGO_ADMIN_EMAIL", "").strip()

    if not username or not password:
        return

    User = get_user_model()
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "email": email,
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        },
    )

    changed = created

    if email and user.email != email:
        user.email = email
        changed = True
    if not user.is_staff:
        user.is_staff = True
        changed = True
    if not user.is_superuser:
        user.is_superuser = True
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True

    reset_password = os.getenv("DJANGO_ADMIN_RESET_PASSWORD", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if created or reset_password:
        user.set_password(password)
        changed = True

    if changed:
        user.save()
