from django.core.cache import caches
from django.db.models.signals import post_delete, post_save
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
