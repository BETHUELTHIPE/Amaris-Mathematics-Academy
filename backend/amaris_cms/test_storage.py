from unittest import TestCase
from urllib.parse import urlsplit

from botocore.exceptions import ParamValidationError
from botocore.stub import Stubber
from storages.backends.s3 import S3Storage

from amaris_cms.storage import SupabaseS3Storage


class SupabaseS3StorageTests(TestCase):
    def storage(self, bucket, backend=SupabaseS3Storage):
        return backend(
            bucket_name=bucket,
            endpoint_url="https://example.storage.supabase.co/storage/v1/s3",
            region_name="us-east-1",
            access_key="synthetic-access",
            secret_key="synthetic-secret",
            addressing_style="path",
            signature_version="s3v4",
        )

    def test_existing_bucket_name_reaches_s3_unchanged(self):
        for bucket in ["Amaris Mathematics Academy", "amaris-cms-files"]:
            with self.subTest(bucket=bucket):
                storage = self.storage(bucket)
                for connection in [storage.connection, storage.unsigned_connection]:
                    with Stubber(connection.meta.client) as stub:
                        stub.add_response(
                            "head_bucket",
                            {"ResponseMetadata": {"HTTPStatusCode": 200}},
                            {"Bucket": bucket},
                        )
                        response = connection.meta.client.head_bucket(Bucket=bucket)
                        self.assertEqual(response["ResponseMetadata"]["HTTPStatusCode"], 200)

    def test_signed_download_encodes_original_bucket_name(self):
        url = self.storage("Amaris Mathematics Academy").url("student/test.pdf")
        self.assertEqual(
            urlsplit(url).path,
            "/storage/v1/s3/Amaris%20Mathematics%20Academy/student/test.pdf",
        )
        self.assertIn("X-Amz-Signature=", urlsplit(url).query)

    def test_invalid_names_and_regular_s3_still_reject(self):
        for storage in [
            self.storage("invalid/bucket"),
            self.storage("Amaris Mathematics Academy", backend=S3Storage),
        ]:
            with self.subTest(backend=type(storage).__name__):
                with self.assertRaises(ParamValidationError):
                    storage.connection.meta.client.head_bucket(Bucket=storage.bucket_name)
