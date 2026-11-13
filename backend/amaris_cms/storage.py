"""Supabase S3 storage supporting existing bucket names with spaces."""

from botocore.handlers import validate_bucket_name
from django.core.files.storage import FileSystemStorage, Storage, storages
from storages.backends.s3 import S3Storage


def validate_supabase_bucket_name(params, **kwargs):
    # Supabase accepts spaces in bucket IDs. Validate a same-length surrogate
    # while keeping the original ID for the request path and signature.
    validation_params = dict(params)
    bucket = validation_params.get("Bucket")
    if isinstance(bucket, str):
        validation_params["Bucket"] = bucket.replace(" ", "-")
    validate_bucket_name(validation_params, **kwargs)


class SupabaseS3Storage(S3Storage):
    def _create_session(self):
        session = super()._create_session()
        session.events.unregister("before-parameter-build.s3", validate_bucket_name)
        session.events.register("before-parameter-build.s3", validate_supabase_bucket_name)
        return session


class UnconfiguredPrivateStorage(Storage):
    """Reject file operations when production S3 credentials are absent."""

    def _unavailable(self, *args, **kwargs):
        raise OSError("Private Supabase storage is not configured; no file was saved locally.")

    _open = _unavailable
    _save = _unavailable
    exists = _unavailable
    delete = _unavailable
    size = _unavailable
    url = _unavailable


class LocalPrivateStorage(FileSystemStorage):
    """Development-only private files must use an authenticated download route."""

    def url(self, name):
        raise ValueError("Private files do not have a public media URL.")


def tutor_private_storage():
    return storages["tutor_private"]


def admin_private_storage():
    return storages["admin_private"]


def role_media_storage():
    return storages["role_media"]


class RoleMediaStorage(Storage):
    """Route server-generated tutor keys separately; retain legacy Admin keys."""

    def backend(self, name):
        return storages["tutor_private" if name.startswith("videos/tutor-uploads/") else "default"]

    def save(self, name, content, max_length=None):
        return self.backend(name).save(name, content, max_length=max_length)

    def _open(self, name, mode="rb"):
        return self.backend(name).open(name, mode)

    def exists(self, name):
        return self.backend(name).exists(name)

    def delete(self, name):
        return self.backend(name).delete(name)

    def size(self, name):
        return self.backend(name).size(name)

    def url(self, name):
        return self.backend(name).url(name)
