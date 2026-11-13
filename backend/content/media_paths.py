"""Server-owned paths determine the media bucket without trusting request input."""

import uuid
from pathlib import PurePath

from django.utils import timezone


def _video_path(instance, filename, category):
    owner = instance.uploaded_by if instance.uploaded_by_id else None
    tutor = owner and not owner.is_superuser and owner.groups.filter(name="Tutors").exists()
    suffix = PurePath(filename).suffix.lower()
    if tutor and owner is not None:
        return f"videos/tutor-uploads/{owner.pk}/{category}/{uuid.uuid4()}{suffix}"
    return f"videos/{category}/{timezone.now():%Y/%m}/{uuid.uuid4()}{suffix}"


def video_source_path(instance, filename):
    return _video_path(instance, filename, "source")


def video_thumbnail_path(instance, filename):
    return _video_path(instance, filename, "thumbnails")


def video_captions_path(instance, filename):
    return _video_path(instance, filename, "captions")
