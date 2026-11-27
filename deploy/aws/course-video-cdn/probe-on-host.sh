#!/usr/bin/env bash
set -euo pipefail
task="$1"
key="$2"
[[ "$task" =~ ^[a-f0-9]{32}$ && "$key" =~ ^academy-media/videos/[a-f0-9]{32}\.mp4$ ]]
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$task"   --filter label=com.amazonaws.ecs.container-name=backend)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
docker exec -i "$backend" python - "$key" <<'PY'
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

for line in os.environ.pop("AMARIS_RUNTIME_ENV", "").splitlines():
    name, sep, value = line.partition("=")
    if sep:
        os.environ.setdefault(name, value)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
import django
django.setup()

from django.conf import settings
from content.models import VideoAsset
from content.services.course_media import _cloudfront_signer, lesson_playback_url

def request(url, headers=None):
    try:
        with urlopen(Request(url, headers=headers or {}), timeout=12) as response:
            return response.status, response.headers, response.read(65536)
    except HTTPError as error:
        return error.code, error.headers, b""

key = sys.argv[1]
url = lesson_playback_url(VideoAsset(provider="s3", aws_media_key=key, is_published=True))
parsed = urlsplit(url)
assert parsed.hostname == settings.ACADEMY_VIDEO_CLOUDFRONT_DOMAIN and parsed.scheme == "https"
bare = url.split("?", 1)[0]
assert request(bare)[0] == 403, "Unsigned CloudFront playback must be rejected"
assert request(f"https://{settings.ACADEMY_MEDIA_BUCKET}.s3.eu-north-1.amazonaws.com/{key}")[0] == 403, "S3 must remain private"

for attempt in range(8):
    code, headers, body = request(url)
    assert code == 200 and headers.get("Content-Type") == "video/mp4" and body[4:8] == b"ftyp", "CloudFront could not serve the MP4"
    if "hit from cloudfront" in (headers.get("X-Cache") or "").lower():
        break
    time.sleep(2)
else:
    raise RuntimeError("CloudFront did not return a cached signed response")

partial, headers, body = request(url, {"Range": "bytes=0-31"})
assert partial == 206 and headers.get("Content-Range", "").startswith("bytes 0-31/") and len(body) == 32
assert request(bare)[0] == 403, "Cache hit must still require a signature"
signer = _cloudfront_signer(settings.ACADEMY_VIDEO_CLOUDFRONT_KEY_ID, settings.ACADEMY_VIDEO_CLOUDFRONT_PRIVATE_KEY)
expired = signer.generate_presigned_url(bare, date_less_than=datetime.now(UTC) - timedelta(minutes=2))
assert request(expired)[0] == 403, "Expired playback must be rejected even when cached"
print("PASS: Django signed the MP4, CloudFront cached it and returned HTTP 206, and unsigned, expired and direct-S3 requests were refused.")
PY
