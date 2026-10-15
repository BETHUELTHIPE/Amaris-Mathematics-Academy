import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


ACCEPTED_SUFFIXES = {
    "image": {".png", ".jpg", ".jpeg", ".webp", ".gif"},
    "video": {".mp4", ".mov", ".webm"},
    "pdf": {".pdf"},
}
MAX_SIZE = {"image": 20 * 1024 * 1024, "video": 100 * 1024 * 1024, "pdf": 25 * 1024 * 1024}


def marketing_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"marketing/announcements/{instance.announcement_id}/{uuid.uuid4().hex}{suffix}"


class AnnouncementMedia(models.Model):
    class MediaType(models.TextChoices):
        IMAGE = "image", "Image"
        VIDEO = "video", "Video"
        PDF = "pdf", "PDF document"

    announcement = models.ForeignKey(
        "content.Announcement", related_name="marketing_media", on_delete=models.CASCADE
    )
    media_type = models.CharField(max_length=8, choices=MediaType.choices)
    file = models.FileField(upload_to=marketing_upload_path)
    caption = models.CharField(max_length=220, blank=True)
    alt_text = models.CharField(max_length=220, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("order", "id")
        verbose_name_plural = "Announcement media"

    def clean(self):
        super().clean()
        if not self.file:
            raise ValidationError({"file": "Upload an image, video or PDF."})
        extension = Path(self.file.name).suffix.lower()
        if extension not in ACCEPTED_SUFFIXES.get(self.media_type, set()):
            raise ValidationError({"file": "The extension does not match the chosen media type."})
        if self.file.size > MAX_SIZE[self.media_type]:
            raise ValidationError({"file": f"File is too large for {self.media_type} uploads."})
        if self.media_type == "image" and not self.alt_text.strip():
            raise ValidationError({"alt_text": "Image alternative text is required for accessibility."})
        # Existing stored files are not re-opened/validated when editing captions.
        if not getattr(self.file, "_committed", True):
            position = self.file.tell()
            self.file.seek(0)
            header = self.file.read(16)
            self.file.seek(position)
            valid = {
                "pdf": header.startswith(b"%PDF-"),
                "image": (
                    header.startswith(b"\x89PNG\r\n\x1a\n")
                    or header.startswith(b"\xff\xd8\xff")
                    or header.startswith((b"GIF87a", b"GIF89a"))
                    or (header.startswith(b"RIFF") and header[8:12] == b"WEBP")
                ),
                "video": (
                    (extension in {".mp4", ".mov"} and header[4:8] == b"ftyp")
                    or (extension == ".webm" and header.startswith(b"\x1a\x45\xdf\xa3"))
                ),
            }
            if not valid[self.media_type]:
                raise ValidationError({"file": "File content does not match its type."})
        if not settings.DEBUG and settings.STORAGES["default"]["BACKEND"] != "storages.backends.s3.S3Storage":
            raise ValidationError("Production marketing uploads require configured CMS S3 storage.")

    def __str__(self):
        return f"{self.get_media_type_display()} for {self.announcement}"
