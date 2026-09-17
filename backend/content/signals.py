from django.core.cache import caches
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import (
    FAQ,
    Announcement,
    ContactEnquiry,
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


@receiver(post_save, sender=ContactEnquiry, dispatch_uid="content.queue_contact_enquiry_auto_reply")
def queue_contact_enquiry_auto_reply(sender, instance, created, raw=False, **_kwargs):
    if not created or raw:
        return

    enquiry_id = instance.pk

    def enqueue() -> None:
        from .tasks import send_contact_enquiry_auto_reply

        send_contact_enquiry_auto_reply.delay(enquiry_id)

    # Do not send an email for a database row that later rolls back. robust=True
    # preserves the submitted enquiry if the broker is temporarily unavailable;
    # Celery/Redis health monitoring remains responsible for surfacing that outage.
    transaction.on_commit(enqueue, robust=True)
