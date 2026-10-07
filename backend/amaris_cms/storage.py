"""Supabase S3 storage supporting existing bucket names with spaces."""

from botocore.handlers import validate_bucket_name
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
