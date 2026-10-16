"""Integration acceptance: real Django superuser upload -> Supabase S3 -> signed byte GET.

Run only with SQLite and trusted main branch, never connected to production DB.
The real private CMS bucket is shared; every synthetic test object is removed.
"""
import hashlib
import os
import secrets
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

import django

if os.getenv("GITHUB_REF") != "refs/heads/main":
    raise SystemExit("BLOCK: only trusted main may use protected S3 secrets")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.files.storage import default_storage  # noqa: E402
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client, override_settings  # noqa: E402
from django.urls import reverse  # noqa: E402

from content.models import Announcement, AnnouncementMedia  # noqa: E402
from verify_supabase_media_roundtrip import BUCKET, ENDPOINT, files  # noqa: E402


def main():
    if connection.vendor != "sqlite":
        raise RuntimeError("BLOCK: live integration test must never use a remote database")
    if settings.CMS_STORAGE_BUCKET_NAME != BUCKET:
        raise RuntimeError("BLOCK: wrong CMS storage bucket")
    if settings.STORAGES["default"]["BACKEND"] != "storages.backends.s3.S3Storage":
        raise RuntimeError("BLOCK: default Django storage is not Supabase S3")
    if settings.AWS_S3_ENDPOINT_URL.rstrip("/") != ENDPOINT:
        raise RuntimeError("BLOCK: wrong S3 endpoint")
    if not settings.STUDENT_STORAGE_BUCKET_NAME:
        raise RuntimeError("BLOCK: student storage config missing")
    if not os.getenv("AWS_ACCESS_KEY_ID") or not os.getenv("AWS_SECRET_ACCESS_KEY"):
        raise RuntimeError("BLOCK: missing secrets")

    import boto3
    from botocore.config import Config

    s3 = boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, read_timeout=12,
                      retries={"total_max_attempts": 2}),
    )
    marker = f"pr207-{os.environ.get('GITHUB_RUN_ID','manual')}-{secrets.token_hex(6)}"
    user_model = get_user_model()
    users = []
    announcement = None
    created = []
    success = False
    try:
        admin = user_model.objects.create_superuser(
            f"ci_super_{marker}", f"ci-{marker}@example.invalid", secrets.token_urlsafe(32))
        staff = user_model.objects.create_user(
            f"ci_staff_{marker}", f"staff-{marker}@example.invalid",
            secrets.token_urlsafe(32), is_staff=True)
        users.extend([admin, staff])
        announcement = Announcement.objects.create(
            title=f"STAGING MARKETING CI {marker}", message="Safe disposable verification.",
            is_published=False,
        )
        payloads = files()
        client = Client(raise_request_exception=False)
        with override_settings(ALLOWED_HOSTS=["testserver", "localhost"]):
            client.force_login(admin)
            for name, (blob, mime) in payloads.items():
                kind = "image" if name.endswith(".png") else "video" if name.endswith(".mp4") else "pdf"
                title = f"{marker}-{kind}"
                response = client.post(
                    reverse("admin:content_announcementmedia_add"),
                    {
                        "announcement": announcement.pk, "kind": kind, "title": title,
                        "file": SimpleUploadedFile(f"{marker}-{name}", blob, content_type=mime),
                        "order": 1, "_save": "Save",
                    }, secure=True,
                )
                if response.status_code != 302:
                    raise RuntimeError(f"{kind}: Django Admin upload HTTP {response.status_code}")
                asset = AnnouncementMedia.objects.get(title=title)
                created.append(asset.file.name)
                if not default_storage.exists(asset.file.name):
                    raise RuntimeError(f"{kind}: S3 object is missing")
                if client.get(reverse("public-marketing-media", args=[asset.pk]), secure=True).status_code != 404:
                    raise RuntimeError(f"{kind}: unpublished asset exposed")
                print(f"PASS Django Admin superuser uploaded {kind} to private S3; draft returns 404")

            client.force_login(staff)
            for asset in AnnouncementMedia.objects.filter(announcement=announcement):
                change = reverse("admin:content_announcementmedia_change", args=[asset.pk])
                if client.get(change, secure=True).status_code != 403:
                    raise RuntimeError("ordinary staff can view marketing admin")
                if client.post(change, {"title": "intrusion"}, secure=True).status_code != 403:
                    raise RuntimeError("ordinary staff can edit marketing admin")
            print("PASS ordinary staff denied GET and POST to marketing admin")

            announcement.is_published = True
            announcement.save(update_fields=["is_published"])
            client.logout()
            for asset in AnnouncementMedia.objects.filter(announcement=announcement):
                response = client.get(reverse("public-marketing-media", args=[asset.pk]), secure=True)
                if response.status_code != 302:
                    raise RuntimeError(f"{asset.kind}: signed download redirect HTTP {response.status_code}")
                signed = response["Location"]
                parsed = urlsplit(signed)
                qs = parse_qs(parsed.query)
                if parsed.scheme != "https" or parsed.hostname != urlsplit(ENDPOINT).hostname:
                    raise RuntimeError(f"{asset.kind}: unexpected signed URL destination")
                if qs.get("X-Amz-Expires") != ["120"] or not qs.get("X-Amz-Signature"):
                    raise RuntimeError(f"{asset.kind}: bad signature or expiry")
                if "no-store" not in response.get("Cache-Control", ""):
                    raise RuntimeError(f"{asset.kind}: signed redirect must not be cached")
                with urlopen(signed, timeout=20) as f:
                    downloaded = f.read()
                raw = payloads[{"image":"image.png","video":"video.mp4","pdf":"document.pdf"}[asset.kind]][0]
                if hashlib.sha256(downloaded).digest() != hashlib.sha256(raw).digest():
                    raise RuntimeError(f"{asset.kind}: signed download bytes differ")
                print(f"PASS Django {asset.kind} publish, 120s private signed redirect, exact SHA256 GET")

            announcement.is_published = False
            announcement.save(update_fields=["is_published"])
            for asset in AnnouncementMedia.objects.filter(announcement=announcement):
                if client.get(reverse("public-marketing-media", args=[asset.pk]), secure=True).status_code != 404:
                    raise RuntimeError(f"{asset.kind}: asset still accessible after unpublish")
            print("PASS unpublishing blocks new signed URL grants")
        success = True
    finally:
        # Delete any partially uploaded objects matching ONLY our unique marker.
        listed = s3.list_objects_v2(Bucket=BUCKET, Prefix="marketing/announcements/")
        scoped = [item["Key"] for item in listed.get("Contents", [])
                  if marker in item["Key"]]
        for name in set(created + scoped):
            default_storage.delete(name)
        remaining = s3.list_objects_v2(Bucket=BUCKET, Prefix="marketing/announcements/")
        leftover = [i["Key"] for i in remaining.get("Contents", []) if marker in i["Key"]]
        if announcement is not None:
            announcement.delete()
        for user in users:
            user.delete()
        if leftover:
            raise RuntimeError("Cleanup failed: temporary S3 objects still exist")
        print("PASS cleanup: all temporary Django rows and S3 media objects deleted")

    if not success:
        raise RuntimeError("Django + Supabase S3 smoke test incomplete")
    print("PASS all real Django Admin/Supabase media journeys")


if __name__ == "__main__":
    main()
