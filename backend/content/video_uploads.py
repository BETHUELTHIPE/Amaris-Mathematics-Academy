"""Private, authenticated, direct-to-Supabase S3 multipart uploads for topic requests.

Large bytes never transit Django/Next checkout. No public bucket or S3 secret is
exposed to the browser. A complete file is recorded only after S3 HEAD validation.
"""
import math
import re
import uuid
from pathlib import PurePosixPath

from django.core.files.storage import storages
from django.db import transaction
from rest_framework import serializers

from .models import VideoRequest, VideoRequestDocument

MAX_REQUEST_BYTES = 1024 * 1024 * 1024  # 1 GiB across all files/folders
MAX_REQUEST_FILES = 200
PART_BYTES = 8 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def validate_file(name, size, content_type):
    if not isinstance(name, str) or not isinstance(size, int):
        raise serializers.ValidationError("A file name and integer size are required.")
    name = name.replace("\\", "/")
    segments = name.split("/")
    if (
        len(name) > 255
        or name.startswith("/")
        or any(segment in {"", ".", ".."} for segment in segments)
        or any(ord(character) < 32 for character in name)
    ):
        raise serializers.ValidationError("Invalid relative file or folder path.")
    extension = PurePosixPath(name).suffix.lower()
    mime = ALLOWED_EXTENSIONS.get(extension)
    if not mime or content_type != mime:
        raise serializers.ValidationError("This file type is not supported for private uploads.")
    if not 0 < size <= MAX_REQUEST_BYTES:
        raise serializers.ValidationError("Each file must be between 1 byte and 1 GiB.")
    return name, size, mime, extension


def _client():
    storage = storages["student_private"]
    if not hasattr(storage, "connection") or not getattr(storage, "bucket_name", ""):
        raise serializers.ValidationError("Large uploads require configured private Supabase S3 storage.")
    return storage.connection.meta.client, storage.bucket_name


def _owned_request(student, reference, lock=False):
    qs = VideoRequest.objects.filter(reference=reference, student=student)
    if lock:
        qs = qs.select_for_update()
    item = qs.first()
    if not item:
        raise serializers.ValidationError("Video request not found.")
    if item.status != VideoRequest.Status.PENDING_PAYMENT:
        raise serializers.ValidationError("Uploads close when payment processing begins.")
    return item


def _prefix(item):
    return f"{item.student.supabase_user_id}/video-requests/{item.pk}/documents/"


def _owned_key(item, key):
    prefix = _prefix(item)
    if not isinstance(key, str) or not re.fullmatch(
        re.escape(prefix) + r"[0-9a-f]{32}\\.[a-z0-9]+", key
    ):
        raise serializers.ValidationError("Invalid private upload key.")
    return key


def _quota(item, new_size):
    docs = item.documents.all()
    if docs.count() >= MAX_REQUEST_FILES:
        raise serializers.ValidationError("Maximum 200 supporting files per request.")
    if sum(doc.size_bytes for doc in docs) + new_size > MAX_REQUEST_BYTES:
        raise serializers.ValidationError("Maximum 1 GiB across all supporting files and folders.")


def begin_upload(student, reference, values):
    name, size, mime, extension = validate_file(
        values.get("name"), values.get("size"), values.get("content_type")
    )
    item = _owned_request(student, reference)
    _quota(item, size)
    client, bucket = _client()
    key = f"{_prefix(item)}{uuid.uuid4().hex}{extension}"
    result = client.create_multipart_upload(
        Bucket=bucket, Key=key, ContentType=mime,
        ContentDisposition="attachment", CacheControl="private, no-store",
    )
    return {
        "key": key,
        "upload_id": result["UploadId"],
        "part_bytes": PART_BYTES,
        "parts": math.ceil(size / PART_BYTES),
        "name": name,
    }


def part_url(student, reference, values):
    item = _owned_request(student, reference)
    key = _owned_key(item, values.get("key"))
    upload_id = values.get("upload_id")
    part_number = values.get("part_number")
    if not isinstance(upload_id, str) or not 1 <= len(upload_id) <= 512:
        raise serializers.ValidationError("Invalid multipart upload ID.")
    if not isinstance(part_number, int) or not 1 <= part_number <= math.ceil(MAX_REQUEST_BYTES / PART_BYTES):
        raise serializers.ValidationError("Invalid multipart part number.")
    client, bucket = _client()
    return {
        "url": client.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": bucket, "Key": key,
                "UploadId": upload_id, "PartNumber": part_number,
            },
            ExpiresIn=900,
            HttpMethod="PUT",
        )
    }


def complete_upload(student, reference, values):
    name, size, mime, extension = validate_file(
        values.get("name"), values.get("size"), values.get("content_type")
    )
    key = values.get("key")
    upload_id = values.get("upload_id")
    parts = values.get("parts")
    if not isinstance(upload_id, str) or not 1 <= len(upload_id) <= 512:
        raise serializers.ValidationError("Invalid multipart upload ID.")
    expected_parts = math.ceil(size / PART_BYTES)
    if (
        not isinstance(parts, list)
        or len(parts) != expected_parts
        or any(
            not isinstance(part, dict)
            or part.get("part_number") != index
            or not isinstance(part.get("etag"), str)
            or not re.fullmatch(r'["A-Za-z0-9_-]{8,128}', part["etag"])
            for index, part in enumerate(parts, 1)
        )
    ):
        raise serializers.ValidationError("Missing or invalid multipart ETags.")
    client, bucket = _client()
    with transaction.atomic():
        item = _owned_request(student, reference, lock=True)
        key = _owned_key(item, key)
        if not key.endswith(extension):
            raise serializers.ValidationError("The uploaded file extension changed.")
        if item.documents.filter(storage_path=key).exists():
            raise serializers.ValidationError("File was already attached.")
        _quota(item, size)
        completed = False
        try:
            client.complete_multipart_upload(
                Bucket=bucket, Key=key, UploadId=upload_id,
                MultipartUpload={"Parts": [
                    {"PartNumber": p["part_number"], "ETag": p["etag"]} for p in parts
                ]},
            )
            completed = True
            head = client.head_object(Bucket=bucket, Key=key)
            if head.get("ContentLength") != size or head.get("ContentType") != mime:
                raise serializers.ValidationError("Uploaded file size or type does not match.")
            # Direct uploads are not hashed in Django; do not manufacture a SHA-256.
            VideoRequestDocument.objects.create(
                request=item, original_name=name, storage_path=key,
                content_type=mime, size_bytes=size, sha256="",
            )
        except Exception:
            if completed:
                client.delete_object(Bucket=bucket, Key=key)
            raise
    return {"name": name, "size": size, "attached": True}


def abort_upload(student, reference, values):
    item = _owned_request(student, reference)
    key = _owned_key(item, values.get("key"))
    upload_id = values.get("upload_id")
    if not isinstance(upload_id, str) or not 1 <= len(upload_id) <= 512:
        raise serializers.ValidationError("Invalid multipart upload ID.")
    client, bucket = _client()
    client.abort_multipart_upload(Bucket=bucket, Key=key, UploadId=upload_id)
    return {"aborted": True}
