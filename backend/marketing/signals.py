from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import AnnouncementMedia


def delete_after_commit(storage, name):
    if name:
        transaction.on_commit(lambda: storage.delete(name))


@receiver(post_delete, sender=AnnouncementMedia)
def delete_removed_media(sender, instance, **kwargs):
    if instance.file:
        delete_after_commit(instance.file.storage, instance.file.name)


@receiver(pre_save, sender=AnnouncementMedia)
def delete_replaced_media(sender, instance, **kwargs):
    if not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).only("file").first()
    if previous and previous.file and previous.file.name != instance.file.name:
        delete_after_commit(previous.file.storage, previous.file.name)
