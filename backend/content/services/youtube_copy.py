"""Copy one approved S3 lesson to the configured YouTube channel."""

import json
import re
from datetime import timedelta
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener

from billiard.exceptions import SoftTimeLimitExceeded
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from content.models import VideoAsset, YouTubeLessonCopy

from .course_media import MAX_BYTES, S3_FORMATS, _NoRedirect, s3_client

API = "https://www.googleapis.com"
UPLOAD_PATH = "/upload/youtube/v3/videos"
CHUNK_SIZE = 8 * 1024 * 1024
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


class CopyError(Exception):
    """An error safe to display in Django Admin."""


def youtube_copy_enabled():
    return bool(
        settings.ACADEMY_MEDIA_BUCKET
        and CHANNEL_ID.fullmatch(settings.ACADEMY_YOUTUBE_CHANNEL_ID)
        and settings.ACADEMY_YOUTUBE_CLIENT_ID
        and settings.ACADEMY_YOUTUBE_CLIENT_SECRET
        and settings.ACADEMY_YOUTUBE_REFRESH_TOKEN
    )


def eligible_source(video):
    key = video.aws_media_key
    return (
        video.provider == VideoAsset.Provider.S3
        and video.is_live
        and key.startswith("academy-media/videos/")
        and PurePosixPath(key).suffix.lower() in S3_FORMATS
    )


def google_request(url, *, method="GET", data=None, token=None, headers=None):
    headers = dict(headers or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        response = build_opener(_NoRedirect()).open(request, timeout=25)
    except HTTPError as error:
        if error.code == 308:
            with error:
                return 308, error.headers, {}
        if error.code == 404 and urlsplit(url).path == UPLOAD_PATH and method == "PUT":
            raise CopyError(
                "The upload session expired. Check YouTube Studio for this copy before making another."
            ) from None
        raise CopyError(f"Google returned HTTP {error.code}. Check the channel credentials and retry.") from None
    with response:
        raw = response.read(1024 * 1024)
        return response.status, response.headers, json.loads(raw) if raw else {}


def access_token(channel):
    data = urlencode(
        {
            "client_id": settings.ACADEMY_YOUTUBE_CLIENT_ID,
            "client_secret": settings.ACADEMY_YOUTUBE_CLIENT_SECRET,
            "refresh_token": settings.ACADEMY_YOUTUBE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        }
    ).encode()
    status, _, result = google_request(
        "https://oauth2.googleapis.com/token",
        method="POST",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = result.get("access_token")
    if status != 200 or not isinstance(token, str) or not token:
        raise CopyError("Google did not issue an upload access token.")
    status, _, result = google_request(f"{API}/youtube/v3/channels?part=id&mine=true", token=token)
    if status != 200 or {item.get("id") for item in result.get("items", [])} != {channel}:
        raise CopyError("The Google credentials do not match the configured Academy channel.")
    return token


def checked_session(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.netloc not in {"www.googleapis.com", "youtube.googleapis.com"}
        or parsed.path != UPLOAD_PATH
        or parsed.fragment
        or not parse_qs(parsed.query).get("upload_id")
    ):
        raise CopyError("Google did not supply a valid upload session address.")
    return url


def begin_session(token, title, size, mime):
    title = title.replace("<", "").replace(">", "").strip()[:100]
    status, headers, _ = google_request(
        f"{API}{UPLOAD_PATH}?uploadType=resumable&part=snippet,status",
        method="POST",
        data=json.dumps(
            {
                "snippet": {"title": title or "Amaris lesson", "categoryId": "27"},
                "status": {"privacyStatus": "private", "embeddable": False},
            }
        ).encode(),
        token=token,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": mime,
        },
    )
    if status != 200:
        raise CopyError("Google did not start the private upload.")
    return checked_session(headers.get("Location", ""))


def resume_position(headers, size):
    range_header = headers.get("Range")
    if not range_header:
        return 0
    match = re.fullmatch(r"bytes=0-(\d+)", range_header)
    if not match or not 0 < int(match[1]) + 1 < size:
        raise CopyError("Google returned an unexpected upload position.")
    return int(match[1]) + 1


def send_file(copy, s3, token, mime):
    size = copy.source_size
    session = checked_session(copy.upload_session)
    status, headers, result = google_request(
        session, method="PUT", data=b"", token=token, headers={"Content-Range": f"bytes */{size}"}
    )
    while status == 308:
        position = resume_position(headers, size)
        end = min(position + CHUNK_SIZE, size) - 1
        response = s3.get_object(
            Bucket=copy.source_bucket,
            Key=copy.source_key,
            IfMatch=copy.source_etag,
            Range=f"bytes={position}-{end}",
        )
        body = response["Body"]
        try:
            chunk = body.read(end - position + 1)
        finally:
            body.close()
        if len(chunk) != end - position + 1:
            raise CopyError("The lesson object returned an incomplete range.")
        status, headers, result = google_request(
            session,
            method="PUT",
            data=chunk,
            token=token,
            headers={"Content-Type": mime, "Content-Range": f"bytes {position}-{end}/{size}"},
        )
        if status == 308 and not position < resume_position(headers, size) <= end + 1:
            raise CopyError("Google did not confirm progress. Retry this copy to resume the same session.")

    video_id = result.get("id")
    if (
        status not in (200, 201)
        or not isinstance(video_id, str)
        or not VIDEO_ID.fullmatch(video_id)
        or (result.get("snippet") or {}).get("channelId") != copy.channel_id
        or (result.get("status") or {}).get("privacyStatus") != "private"
        or (result.get("status") or {}).get("embeddable") is not False
    ):
        raise CopyError(
            "The provider response did not confirm a private copy on the Academy channel. Check YouTube Studio."
        )
    return video_id


def claim_copy(copy_id):
    with transaction.atomic():
        copy = YouTubeLessonCopy.objects.select_for_update().filter(pk=copy_id).first()
        now = timezone.now()
        if copy is None or copy.status == copy.Status.COMPLETE or (copy.lease_until and copy.lease_until > now):
            return None
        copy.status = copy.Status.COPYING
        copy.issue = ""
        # Keep the lease longer than the worker's hard task limit.
        copy.lease_until = now + timedelta(seconds=settings.CELERY_TASK_TIME_LIMIT + 120)
        copy.save(update_fields=["status", "issue", "lease_until", "updated_at"])
        return copy


def perform_youtube_copy(copy_id):
    copy = claim_copy(copy_id)
    if copy is None:
        return
    try:
        if (
            not youtube_copy_enabled()
            or copy.channel_id != settings.ACADEMY_YOUTUBE_CHANNEL_ID
            or copy.source_bucket != settings.ACADEMY_MEDIA_BUCKET
            or not eligible_source(copy.video)
            or copy.video.aws_media_key != copy.source_key
        ):
            raise CopyError("The selected lesson or configured channel has changed. Review the video record.")
        s3 = s3_client()
        obj = s3.head_object(Bucket=copy.source_bucket, Key=copy.source_key)
        size, etag = obj["ContentLength"], obj["ETag"]
        if not 0 < size <= MAX_BYTES or not etag:
            raise CopyError("Choose a non-empty S3 video of up to 4 GiB.")
        if copy.source_etag and (copy.source_etag, copy.source_size) != (etag, size):
            raise CopyError("The S3 video changed since the copy started. Review the source before continuing.")
        token = access_token(copy.channel_id)
        mime = S3_FORMATS[PurePosixPath(copy.source_key).suffix.lower()]
        if not copy.upload_session:
            copy.upload_session = begin_session(token, copy.video.title, size, mime)
            copy.source_etag, copy.source_size = etag, size
            copy.save(update_fields=["upload_session", "source_etag", "source_size", "updated_at"])
        copy.youtube_video_id = send_file(copy, s3, token, mime)
        copy.upload_session = ""
        copy.status = copy.Status.COMPLETE
    except CopyError as error:
        copy.issue = str(error)
        copy.status = copy.Status.FAILED
    except (BotoCoreError, ClientError, URLError, OSError, ValueError, SoftTimeLimitExceeded):
        copy.issue = "The private copy was interrupted. Select the same video and retry to resume."
        copy.status = copy.Status.FAILED
    finally:
        copy.lease_until = None
        copy.save(update_fields=["status", "issue", "lease_until", "youtube_video_id", "upload_session", "updated_at"])
