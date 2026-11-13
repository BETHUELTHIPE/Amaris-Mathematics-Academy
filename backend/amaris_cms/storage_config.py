"""Keep CMS/tutor and student files in their designated private Supabase buckets."""

from pathlib import Path

ADMIN_BUCKET = "amaris-cms-files"
STUDENT_BUCKET = "Amaris Mathematics Academy"


def build_storage_config(
    *,
    debug: bool,
    required: bool,
    base_dir: Path,
    media_root: Path,
    endpoint: str,
    access_key: str,
    secret_key: str,
    admin_bucket: str,
    student_bucket: str,
    region: str,
    legacy_cms_prefix: bool,
) -> dict:
    values = (endpoint, access_key, secret_key, admin_bucket, student_bucket)
    if required or any(values):
        if not all(values) or not endpoint.startswith("https://"):
            raise RuntimeError(
                "Both private Supabase S3 buckets, HTTPS endpoint, and server-side S3 keys are required."
            )
        if admin_bucket != ADMIN_BUCKET or student_bucket != STUDENT_BUCKET:
            raise RuntimeError(f"CMS/tutor files must use {ADMIN_BUCKET}; student files must use {STUDENT_BUCKET}.")
        options = {
            "endpoint_url": endpoint,
            "region_name": region,
            "access_key": access_key,
            "secret_key": secret_key,
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 300,
        }
        admin = {
            "BACKEND": "amaris_cms.storage.SupabaseS3Storage",
            "OPTIONS": {
                **options,
                "bucket_name": ADMIN_BUCKET,
                "file_overwrite": False,
                # Preserve the existing key prefix for backwards-compatible reads.
                "location": "cms" if legacy_cms_prefix else "",
            },
        }
        student = {
            "BACKEND": "amaris_cms.storage.SupabaseS3Storage",
            "OPTIONS": {**options, "bucket_name": STUDENT_BUCKET, "file_overwrite": True},
        }
        tutor = qualifications = admin
    elif debug:
        admin = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
        student = {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": media_root / "student-private", "allow_overwrite": True},
        }
        tutor = {
            "BACKEND": "amaris_cms.storage.LocalPrivateStorage",
            "OPTIONS": {"location": base_dir / "private-tutor-files"},
        }
        qualifications = {
            "BACKEND": "amaris_cms.storage.LocalPrivateStorage",
            "OPTIONS": {"location": base_dir / "private-tutor-qualifications"},
        }
    else:
        # The rest of the site can start, but uploads cannot silently land on
        # ephemeral/public disk. REQUIRED=true also blocks startup above.
        admin = student = tutor = qualifications = {"BACKEND": "amaris_cms.storage.UnconfiguredPrivateStorage"}
    return {
        "default": admin,
        "tutor_private": tutor,
        "tutor_qualifications": qualifications,
        "student_private": student,
        "student_data": student,
        "student_documents": student,
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }
