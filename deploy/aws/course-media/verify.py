"""Verify the exact Django presign path against the staging AWS media bucket."""

import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import django

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
django.setup()

from content.services.course_media import (
    begin_video_upload,
    s3_client,
    verify_video_upload,
)

ORIGIN = "https://16.171.164.5"
BUCKET = os.environ["ACADEMY_MEDIA_BUCKET"]
body = b"disposable academy media infrastructure fixture"
upload = begin_video_upload(
    user_id="staging-probe",
    asset_id="",
    provider="s3",
    filename="probe.mp4",
    size=len(body),
    title="Staging infrastructure smoke",
)
url = upload["url"]
key = urlsplit(url).path.lstrip("/")
if not key.startswith("academy-media/videos/"):
    raise RuntimeError("Unexpected probe object key")
client = s3_client()
version = None
try:
    with urlopen(
        Request(
            url,
            method="OPTIONS",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "content-type,if-none-match,x-amz-server-side-encryption",
            },
        ),
        timeout=12,
    ) as response:
        assert response.headers.get("Access-Control-Allow-Origin") == ORIGIN
    request = Request(
        url, data=body, method="PUT", headers={**upload["headers"], "Origin": ORIGIN}
    )
    with urlopen(request, timeout=20) as response:
        version = response.headers.get("x-amz-version-id")
        assert response.headers.get("Access-Control-Allow-Origin") == ORIGIN
    assert (
        verify_video_upload(
            upload["ticket"], user_id="staging-probe", asset_id="", provider="s3"
        )
        == key
    )
    get_url = client.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=60
    )
    with urlopen(get_url, timeout=12) as response:
        assert (
            response.read() == body
            and response.headers.get("x-amz-server-side-encryption") == "AES256"
        )
    try:
        urlopen(Request(url.split("?")[0]), timeout=12).close()
    except HTTPError as exc:
        assert exc.code == 403
    else:
        raise AssertionError("Unsigned download unexpectedly succeeded")
    try:
        urlopen(request, timeout=12).close()
    except HTTPError as exc:
        assert exc.code == 412
    else:
        raise AssertionError("The same upload link could replace the verified file")
    print(
        "AWS S3 staging passed CORS, signed upload, exact byte read, encryption, private access and replay checks."
    )
finally:
    if version:
        client.delete_object(Bucket=BUCKET, Key=key, VersionId=version)
        print("Removed the isolated staging test object version.")
