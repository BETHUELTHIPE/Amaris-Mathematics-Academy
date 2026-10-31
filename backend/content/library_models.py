"""Shared teaching documents; served only through authorized Library endpoints."""

import uuid
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

LIBRARY_MAX_BYTES = 50 * 1024 * 1024
LIBRARY_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
}


def validate_library_file(value):
    extension = Path(value.name).suffix.lower()
    if extension not in LIBRARY_TYPES:
        raise ValidationError("Choose a PDF, DOCX, XLSX, PPTX or TXT document.")
    if not 0 < value.size <= LIBRARY_MAX_BYTES:
        raise ValidationError("Documents must be non-empty and no larger than 50 MB.")
    position = value.tell()
    try:
        value.seek(0)
        header = value.read(1024)
        if extension == ".pdf" and not header.startswith(b"%PDF-"):
            raise ValidationError("The document is not a valid PDF.")
        if extension == ".txt":
            value.seek(0)
            try:
                # Keep validation memory bounded even for large worksheets.
                import codecs

                decoder = codecs.getincrementaldecoder("utf-8")()
                while chunk := value.read(65536):
                    if b"\x00" in chunk:
                        raise UnicodeError
                    decoder.decode(chunk)
                decoder.decode(b"", final=True)
            except UnicodeError as exc:
                raise ValidationError("Text documents must contain UTF-8 text.") from exc
        if extension in (".docx", ".xlsx", ".pptx"):
            prefix = {".docx": "word/", ".xlsx": "xl/", ".pptx": "ppt/"}[extension]
            try:
                value.seek(0)
                with ZipFile(value) as archive:
                    names = archive.namelist()
                    if "[Content_Types].xml" not in names or not any(name.startswith(prefix) for name in names):
                        raise ValidationError("The Office document format does not match its filename.")
                    if any(name.lower().endswith("vbaproject.bin") for name in names):
                        raise ValidationError("Macro-enabled documents are not supported.")
            except BadZipFile as exc:
                raise ValidationError("The Office document could not be read.") from exc
    finally:
        value.seek(position)


def library_upload_path(instance, filename):
    # Never use a user-controlled folder or filename for storage keys.
    return f"library/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class LibraryResource(models.Model):
    class Kind(models.TextChoices):
        TEXTBOOK = "textbook", "Textbook"
        WORKSHEET = "worksheet", "Worksheet"
        NOTES = "notes", "Study notes"
        OTHER = "other", "Other document"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True, max_length=2000)
    resource_type = models.CharField(max_length=20, choices=Kind.choices)
    subject = models.CharField(max_length=100)
    level = models.CharField(max_length=100, help_text="For example Grade 12, N3 or MAT1512")
    file = models.FileField(upload_to=library_upload_path, validators=[validate_library_file])
    original_name = models.CharField(max_length=255, editable=False)
    size_bytes = models.PositiveBigIntegerField(editable=False)
    content_type = models.CharField(max_length=100, editable=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, editable=False)
    sharing_permitted = models.BooleanField(
        default=False, help_text="I have permission to share this document with students."
    )
    is_published = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name = "Library resource"
        verbose_name_plural = "Library"

    def clean(self):
        super().clean()
        if not self.sharing_permitted:
            raise ValidationError({"sharing_permitted": "Confirm permission to share this document with students."})

    def save(self, *args, **kwargs):
        if self.file and not self.file._committed:
            validate_library_file(self.file)
            self.original_name = Path(self.file.name).name[:255]
            self.size_bytes = self.file.size
            self.content_type = LIBRARY_TYPES[Path(self.file.name).suffix.lower()]
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title
